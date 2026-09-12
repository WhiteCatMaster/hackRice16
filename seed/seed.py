"""Push the generated dataset into Nessie.

Notes that cost real time if you learn them the hard way:

* Order matters. Transactions go in chronologically and the funding deposit goes
  first, because Nessie rejects a withdrawal that would overdraw an account.
* Accounts are created at balance 0 and left to Nessie's own arithmetic, then
  reconciled. If Nessie's model of a credit-card balance disagrees with ours we
  find out here, at seed time, not on stage.
* Every created id is written to `id_map` immediately, so an interrupted run can
  be resumed with --resume instead of duplicating everything in the sandbox.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

from backend.nessie import db
from backend.nessie.client import NessieClient, NessieError
from backend.nessie.timestamps import encode
from seed.generator import Dataset, build
from seed.validate import validate


def opening_floats(ds: Dataset) -> dict[str, float]:
    """How much each account must be opened with so no push is ever rejected.

    Nessie refuses a withdrawal or purchase that would take an account negative,
    and two things in our data legitimately would: credit-card purchases (Nessie
    has no notion of a card balance being debt) and an up-front tuition payment
    that lands before the first stipend. So we walk each account's timeline, find
    its worst point, and open it with exactly that much headroom. The headroom is
    removed again by the balance reconciliation at the end.
    """
    timeline: dict[str, list[tuple[str, int, float]]] = {}

    def add(account: str, when: str, rank: int, delta: float):
        timeline.setdefault(account, []).append((when, rank, delta))

    for d in ds.deposits:
        add(d["account_local_id"], d["transaction_date"], 0, d["amount"])
    for t in ds.transfers:
        add(t["payer_local_id"], t["transaction_date"], 1, -t["amount"])
        add(t["payee_local_id"], t["transaction_date"], 1, t["amount"])
    for w in ds.withdrawals:
        add(w["account_local_id"], w["transaction_date"], 2, -w["amount"])
    for p in ds.purchases:
        add(p["account_local_id"], p["purchase_date"], 3, -p["amount"])

    floats: dict[str, float] = {}
    for account, events in timeline.items():
        balance, lowest = 0.0, 0.0
        for _, _, delta in sorted(events):
            balance += delta
            lowest = min(lowest, balance)
        floats[account] = round(-lowest, 2) if lowest < 0 else 0.0
    return floats


class Pusher:
    def __init__(self, client: NessieClient, conn, resume: bool = False, verbose: bool = True):
        self.client, self.conn, self.verbose = client, conn, verbose
        self.map: dict[str, str] = {}
        self.created = 0
        self.skipped = 0
        if resume:
            self.map = {r["local_id"]: r["nessie_id"]
                        for r in conn.execute("SELECT local_id, nessie_id FROM id_map")}
            if self.map and verbose:
                print(f"resuming: {len(self.map)} objects already in Nessie")

    def remember(self, entity: str, local_id: str, nessie_id: str):
        self.map[local_id] = nessie_id
        self.conn.execute(
            "INSERT OR REPLACE INTO id_map (entity, local_id, nessie_id) VALUES (?,?,?)",
            (entity, local_id, nessie_id),
        )
        self.conn.commit()

    def push(self, entity: str, local_id: str, fn) -> str | None:
        if local_id in self.map:
            self.skipped += 1
            return self.map[local_id]
        nessie_id = fn()
        if not nessie_id:
            raise NessieError("POST", entity, None, f"no id returned for {local_id}")
        self.remember(entity, local_id, nessie_id)
        self.created += 1
        if self.verbose and self.created % 25 == 0:
            print(f"  ...{self.created} objects created")
        return nessie_id

    def ref(self, local_id: str) -> str:
        try:
            return self.map[local_id]
        except KeyError:
            raise NessieError("ref", local_id, None, f"{local_id} was never created") from None


def api_medium(medium: str) -> str:
    """Nessie's purchase medium enum is only balance|rewards.

    Our dataset says "credit" for card spend, which the engine's utilization and
    card-testing logic rely on, so the translation happens here at the push
    boundary and the local cache keeps the finer distinction. Upstream the
    account is already a Credit Card, and "balance" there means funded from the
    account rather than from rewards points.
    """
    return "balance" if medium == "credit" else medium


def push_dataset(ds: Dataset, client: NessieClient, conn, resume: bool = False,
                 limit_purchases: int | None = None, verbose: bool = True) -> Pusher:
    p = Pusher(client, conn, resume=resume, verbose=verbose)

    floats = opening_floats(ds)

    def say(message: str):
        if verbose:
            print(message)

    say("creating merchants...")

    def merchant_payload(m: dict, category_as_list: bool) -> dict:
        return {
            "name": m["name"],
            "category": [m["category"]] if category_as_list else m["category"],
            "address": {"street_number": m["street"].split(" ")[0] if m.get("street") else "1",
                        "street_name": " ".join(m.get("street", "Main St").split(" ")[1:]) or "Main St",
                        "city": m.get("city", "Omaha"), "state": m.get("state", "NE"),
                        "zip": m.get("zip", "68102")},
            "geocode": {"lat": m["lat"], "lng": m["lng"]},
        }

    # The live sandbox returns `category` as a plain string, but the docs imply a
    # list. Rather than guess wrong and lose the run on the first POST, try one
    # shape and fall back to the other.
    def create_merchant(m: dict) -> str:
        nonlocal category_as_list
        try:
            return client.create_merchant(merchant_payload(m, category_as_list))
        except NessieError as exc:
            if exc.status != 400:
                raise
            category_as_list = not category_as_list
            say(f"  merchant category rejected as "
                f"{'a list' if not category_as_list else 'a string'}; "
                f"retrying as {'a list' if category_as_list else 'a string'}")
            return client.create_merchant(merchant_payload(m, category_as_list))

    category_as_list = True
    for m in ds.merchants:
        p.push("merchant", m["local_id"], lambda m=m: create_merchant(m))

    say("creating customers and accounts...")
    for c in ds.customers:
        p.push("customer", c["local_id"], lambda c=c: client.create_customer({
            "first_name": c["first_name"], "last_name": c["last_name"], "address": c["address"],
        }))
    for a in ds.accounts:
        p.push("account", a["local_id"], lambda a=a: client.create_account(
            p.ref(a["customer_local_id"]),
            {"type": a["type"], "nickname": a["nickname"],
             "rewards": int(a.get("rewards") or 0),
             "balance": floats.get(a["local_id"], 0.0)},
        ))

    say("creating bills...")
    for b in ds.bills:
        p.push("bill", b["local_id"], lambda b=b: client.create_bill(
            p.ref(b["account_local_id"]),
            # No creation_date: Nessie sets it server-side and rejects it as an
            # extra field. payment_date already falls back to it, so nothing is
            # lost upstream, and the local cache keeps creation_date regardless.
            {"status": b["status"], "payee": b["payee"], "nickname": b["nickname"],
             "payment_amount": b["payment_amount"],
             "payment_date": b["payment_date"] or b["creation_date"],
             "recurring_date": b["recurring_date"]},
        ))

    # Chronological, all entity types interleaved: the funding deposit has to land
    # before the spending that depends on it.
    timeline: list[tuple[str, str, dict]] = []
    kept = 0
    for d in ds.deposits:
        timeline.append((d["transaction_date"], "deposit", d))
    for w in ds.withdrawals:
        timeline.append((w["transaction_date"], "withdrawal", w))
    for t in ds.transfers:
        timeline.append((t["transaction_date"], "transfer", t))
    for pu in sorted(ds.purchases, key=lambda x: x["purchase_date"]):
        if limit_purchases is not None and kept >= limit_purchases:
            continue
        kept += 1
        timeline.append((pu["purchase_date"], "purchase", pu))
    timeline.sort(key=lambda row: (row[0], {"deposit": 0, "transfer": 1, "withdrawal": 2, "purchase": 3}[row[1]]))

    say(f"creating {len(timeline)} transactions in date order...")
    for _, kind, item in timeline:
        if kind == "deposit":
            p.push("deposit", item["local_id"], lambda i=item: client.create_deposit(
                p.ref(i["account_local_id"]),
                {"medium": i["medium"], "transaction_date": i["transaction_date"],
                 "status": i["status"], "amount": i["amount"],
                 "description": encode(i["description"], i.get("occurred_at"))},
            ))
        elif kind == "withdrawal":
            p.push("withdrawal", item["local_id"], lambda i=item: client.create_withdrawal(
                p.ref(i["account_local_id"]),
                {"medium": i["medium"], "transaction_date": i["transaction_date"],
                 "status": i["status"], "amount": i["amount"],
                 "description": encode(i["description"], i.get("occurred_at"))},
            ))
        elif kind == "transfer":
            p.push("transfer", item["local_id"], lambda i=item: client.create_transfer(
                p.ref(i["payer_local_id"]),
                # This deployment's TransferCreate rejects medium and payee_id as
                # extra fields, and drops payee_id even as a query param: a live
                # transfer records only the payer. So the payee stays local-only,
                # like the other fields Nessie has no room for. Every read goes
                # through the cache, so known_payee() is unaffected -- but the
                # "new payee" scam signal cannot be rebuilt from Nessie alone.
                {"amount": i["amount"], "transaction_date": i["transaction_date"],
                 "status": i["status"],
                 "description": encode(i["description"], i.get("occurred_at"))},
            ))
        else:
            p.push("purchase", item["local_id"], lambda i=item: client.create_purchase(
                p.ref(i["account_local_id"]),
                {"merchant_id": p.ref(i["merchant_local_id"]), "medium": api_medium(i["medium"]),
                 "purchase_date": i["purchase_date"], "amount": i["amount"],
                 "status": i["status"],
                 "description": encode(i["description"], i.get("occurred_at"))},
            ))

    say(f"created {p.created} objects ({p.skipped} already existed)")
    return p


def reconcile_balances(ds: Dataset, client: NessieClient, pusher: Pusher,
                       fix: bool = True) -> list[dict]:
    """Compare what Nessie computed against what the demo needs, and optionally correct it.

    Nessie's balance arithmetic is its own; notably it has no concept of a credit
    card balance being debt. Where it disagrees, our cached value is the one the
    app shows, so we push a correction and report every delta rather than hiding it.
    """
    report = []
    floats = opening_floats(ds)
    for a in ds.accounts:
        if a["local_id"] not in pusher.map:
            continue
        nessie_id = pusher.map[a["local_id"]]
        try:
            live = client.get(f"/accounts/{nessie_id}")
        except NessieError as exc:
            report.append({"account": a["nickname"], "error": str(exc)})
            continue
        headroom = floats.get(a["local_id"], 0.0)
        raw = float((live or {}).get("balance") or 0)
        intended = float(a["balance"])
        # `delta` answers "does Nessie's arithmetic agree with ours?"; the headroom
        # we opened the account with has to come back out either way.
        row = {"account": a["nickname"], "intended": intended,
               "nessie": round(raw - headroom, 2), "opening_float": headroom,
               "delta": round(raw - headroom - intended, 2), "corrected": False}
        if fix and abs(raw - intended) >= 0.01:
            try:
                client.put(f"/accounts/{nessie_id}",
                           {"nickname": a["nickname"], "balance": intended})
                row["corrected"] = True
            except NessieError as exc:
                row["error"] = str(exc)
        report.append(row)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the demo dataset and optionally push it to Nessie.")
    parser.add_argument("--push", action="store_true", help="push to Nessie (default: local cache only)")
    parser.add_argument("--resume", action="store_true", help="skip objects already in id_map")
    parser.add_argument("--as-of", type=date.fromisoformat, help="override the demo 'today'")
    parser.add_argument("--limit-purchases", type=int, help="push only the first N purchases (fast smoke test)")
    parser.add_argument("--no-fix-balances", action="store_true", help="report balance deltas but do not correct them")
    parser.add_argument("--skip-validate", action="store_true")
    args = parser.parse_args()

    print("generating dataset...")
    ds = build(as_of=args.as_of)

    if not args.skip_validate:
        result = validate(ds)
        print(result.report())
        if not result.ok():
            print("\nvalidation failed, refusing to seed. Fix personas.json and re-run.")
            return 1

    conn = db.connect()
    db.init(conn)

    if args.push:
        client = NessieClient(verbose=False)
        reachable, why = client.ping()
        if not reachable:
            print(f"\ncannot reach Nessie: {why}")
            print("Set NESSIE_API_KEY in .env. The local cache still works without it.")
            return 1
        try:
            pusher = push_dataset(ds, client, conn, resume=args.resume,
                                  limit_purchases=args.limit_purchases)
        except NessieError as exc:
            print(f"\nseed failed: {exc}")
            print("Progress is saved. Re-run with --resume once the cause is fixed.")
            return 1

        print("\nreconciling balances...")
        for row in reconcile_balances(ds, client, pusher, fix=not args.no_fix_balances):
            if "error" in row:
                print(f"  {row['account']}: {row['error']}")
            else:
                flag = " (corrected)" if row["corrected"] else ""
                print(f"  {row['account']}: intended {row['intended']:.2f}, "
                      f"Nessie {row['nessie']:.2f}, delta {row['delta']:+.2f}{flag}")
        print(f"\n{client.calls} API calls")

    from backend.nessie.sync import load_local, sync_from_nessie
    if args.push:
        print("\npulling it back into the local cache...")
        counts = sync_from_nessie(conn, verbose=False)
    else:
        counts = load_local(ds, conn)

    print("\ncache ready:")
    for table, n in counts.items():
        print(f"  {table:<12} {n}")
    print("\nExport mocks for the rest of the team with:  python -m seed.export_mocks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
