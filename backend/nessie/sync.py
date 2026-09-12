"""Fill the local SQLite cache.

Two sources, same destination:

  load_local(ds)      the generated dataset straight into SQLite. No network.
                      This is what unblocks P2/P3/P4 and what the demo runs on.

  sync_from_nessie()  poll Nessie and mirror it locally. Nessie has no webhooks,
                      so this is how new transactions reach us. Local-only fields
                      (credit limits, timestamps, scam labels) are re-attached
                      from the generated dataset via the id_map written by seed.py.

Every read in the app goes through the cache, never straight to Nessie, so a slow
or down API during the demo changes nothing.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime

from seed.generator import Dataset, build

from . import db
from .client import NessieClient, NessieError
from .timestamps import decode


# ------------------------------------------------------------------ local load

def load_local(ds: Dataset, conn=None, source: str = "local") -> dict[str, int]:
    """Write the generated dataset into SQLite using local ids as primary keys."""
    conn = conn or db.connect()
    db.init(conn)
    started = datetime.now().isoformat(timespec="seconds")

    mapping = _id_mapping(conn)

    def resolve(local_id: str | None) -> str | None:
        if local_id is None:
            return None
        return mapping.get(local_id, local_id)

    db.upsert(conn, "customers", [
        {**c, "id": resolve(c["local_id"])} for c in ds.customers
    ])
    db.upsert(conn, "accounts", [
        {**a, "id": resolve(a["local_id"]), "customer_id": resolve(a["customer_local_id"])}
        for a in ds.accounts
    ])
    db.upsert(conn, "merchants", [
        {**m, "id": resolve(m["local_id"])} for m in ds.merchants
    ])
    db.upsert(conn, "purchases", [
        {**p, "id": resolve(p["local_id"]), "account_id": resolve(p["account_local_id"]),
         "merchant_id": resolve(p["merchant_local_id"])}
        for p in ds.purchases
    ])
    db.upsert(conn, "bills", [
        {**b, "id": resolve(b["local_id"]), "account_id": resolve(b["account_local_id"])}
        for b in ds.bills
    ])
    db.upsert(conn, "deposits", [
        {**d, "id": resolve(d["local_id"]), "account_id": resolve(d["account_local_id"])}
        for d in ds.deposits
    ])
    db.upsert(conn, "withdrawals", [
        {**w, "id": resolve(w["local_id"]), "account_id": resolve(w["account_local_id"])}
        for w in ds.withdrawals
    ])
    db.upsert(conn, "transfers", [
        {**t, "id": resolve(t["local_id"]), "payer_id": resolve(t["payer_local_id"]),
         "payee_id": resolve(t["payee_local_id"])}
        for t in ds.transfers
    ])

    db.rebuild_payees(conn)
    db.set_meta(conn, "as_of", ds.as_of.isoformat())
    db.set_meta(conn, "calibration", ds.calibration)
    db.set_meta(conn, "scenarios", ds.scenarios)

    counts = db.counts(conn)
    conn.execute(
        "INSERT INTO sync_runs (started_at, finished_at, source, rows, api_calls, note) "
        "VALUES (?,?,?,?,?,?)",
        (started, datetime.now().isoformat(timespec="seconds"), source,
         sum(counts.values()), 0, "generated dataset"),
    )
    conn.commit()
    return counts


def _id_mapping(conn) -> dict[str, str]:
    return {r["local_id"]: r["nessie_id"] for r in conn.execute("SELECT local_id, nessie_id FROM id_map")}


# ----------------------------------------------------------------- nessie pull

def sync_from_nessie(conn=None, client: NessieClient | None = None, verbose: bool = True) -> dict[str, int]:
    """Mirror Nessie into SQLite, preserving the fields Nessie does not know about."""
    conn = conn or db.connect()
    db.init(conn)
    client = client or NessieClient()
    started = datetime.now().isoformat(timespec="seconds")

    mapping = _id_mapping(conn)
    if not mapping:
        raise RuntimeError(
            "No id_map rows: nothing has been pushed to Nessie yet. "
            "Run `python -m seed.seed --push` first, or use `--source local`."
        )
    reverse = {nessie: local for local, nessie in mapping.items()}

    # The generator is deterministic, so re-running it reproduces exactly the
    # local-only fields that belong to each seeded record.
    local = build()
    locals_by_id = {
        "purchases": {p["local_id"]: p for p in local.purchases},
        "bills": {b["local_id"]: b for b in local.bills},
        "deposits": {d["local_id"]: d for d in local.deposits},
        "withdrawals": {w["local_id"]: w for w in local.withdrawals},
        "transfers": {t["local_id"]: t for t in local.transfers},
        "customers": {c["local_id"]: c for c in local.customers},
        "accounts": {a["local_id"]: a for a in local.accounts},
        "merchants": {m["local_id"]: m for m in local.merchants},
    }

    def extras(entity: str, nessie_id: str, keys: list[str]) -> dict:
        row = locals_by_id[entity].get(reverse.get(nessie_id, ""), {})
        return {k: row[k] for k in keys if k in row}

    def say(msg):
        if verbose:
            print(msg)

    say("syncing customers and accounts...")
    customers = client.customers()
    db.upsert(conn, "customers", [
        {"id": c["_id"], "local_id": reverse.get(c["_id"]),
         "first_name": c.get("first_name"), "last_name": c.get("last_name"),
         "address": c.get("address"),
         **extras("customers", c["_id"], [
             "persona_key", "language", "home_currency", "fx_rate", "home_city",
             "home_lat", "home_lng", "arrival_date", "flight_home_date", "is_demo_persona"])}
        for c in customers
    ])

    accounts = []
    for customer in customers:
        if customer["_id"] not in reverse:
            continue  # someone else's data in the shared sandbox
        accounts.extend(client.customer_accounts(customer["_id"]))
    db.upsert(conn, "accounts", [
        {"id": a["_id"], "local_id": reverse.get(a["_id"]),
         "customer_id": a.get("customer_id"), "type": a.get("type"),
         "nickname": a.get("nickname"), "rewards": a.get("rewards"), "balance": a.get("balance"),
         **extras("accounts", a["_id"], ["credit_limit", "apr", "statement_day", "is_frozen", "frozen_reason"])}
        for a in accounts
    ])

    say("syncing merchants...")
    merchants = [m for m in client.merchants() if m.get("_id") in reverse]
    db.upsert(conn, "merchants", [
        {"id": m["_id"], "local_id": reverse.get(m["_id"]), "name": m.get("name"),
         "category": (m.get("category") or [None])[0] if isinstance(m.get("category"), list) else m.get("category"),
         "address": m.get("address"),
         "lat": (m.get("geocode") or {}).get("lat"), "lng": (m.get("geocode") or {}).get("lng"),
         **extras("merchants", m["_id"], ["is_online", "risk_tag"])}
        for m in merchants
    ])

    rows = 0
    for account in accounts:
        account_id = account["_id"]
        say(f"syncing transactions for {account.get('nickname') or account_id}...")

        purchases = []
        for p in client.purchases(account_id):
            description, occurred = decode(p.get("description"), p.get("purchase_date"))
            purchases.append({
                "id": p["_id"], "local_id": reverse.get(p["_id"]), "account_id": account_id,
                "merchant_id": p.get("merchant_id"), "amount": p.get("amount"),
                "purchase_date": p.get("purchase_date"), "status": p.get("status"),
                "medium": p.get("medium"), "description": description,
                "occurred_at": occurred,
                **extras("purchases", p["_id"], ["category", "is_recurring", "label", "scenario"]),
            })
        rows += db.upsert(conn, "purchases", purchases)

        rows += db.upsert(conn, "bills", [
            {"id": b["_id"], "local_id": reverse.get(b["_id"]), "account_id": account_id,
             "status": b.get("status"), "payee": b.get("payee"), "nickname": b.get("nickname"),
             "payment_amount": b.get("payment_amount"), "payment_date": b.get("payment_date"),
             "recurring_date": b.get("recurring_date"), "creation_date": b.get("creation_date"),
             "upcoming_payment_date": b.get("upcoming_payment_date"),
             **extras("bills", b["_id"], [
                 "category", "cadence", "explanation", "is_trial",
                 "trial_converts_on", "trial_amount_after"])}
            for b in client.bills(account_id)
        ])

        for entity, fetch, date_field in (
            ("deposits", client.deposits, "transaction_date"),
            ("withdrawals", client.withdrawals, "transaction_date"),
        ):
            batch = []
            for item in fetch(account_id):
                description, occurred = decode(item.get("description"), item.get(date_field))
                batch.append({
                    "id": item["_id"], "local_id": reverse.get(item["_id"]), "account_id": account_id,
                    "type": item.get("type"), "transaction_date": item.get(date_field),
                    "status": item.get("status"), "medium": item.get("medium"),
                    "amount": item.get("amount"), "description": description,
                    "occurred_at": occurred,
                    **extras(entity, item["_id"], ["category", "is_recurring"]),
                })
            rows += db.upsert(conn, entity, batch)

        transfers = []
        for t in client.transfers(account_id):
            description, occurred = decode(t.get("description"), t.get("transaction_date"))
            # Nessie stores no payee and no medium on a transfer, so both come
            # back None. Taking them at face value would blank the payee column
            # and rebuild_payees() below would then erase every payee history --
            # which is what "have you paid this person before?" is built on.
            # Re-attach them from the deterministic generator, same as any other
            # field the API has no room for.
            local_row = locals_by_id["transfers"].get(reverse.get(t["_id"], ""), {})
            payee_local = local_row.get("payee_local_id")
            transfers.append({
                "id": t["_id"], "local_id": reverse.get(t["_id"]),
                "payer_id": t.get("payer_id") or account_id,
                "payee_id": mapping.get(payee_local, payee_local) if payee_local else t.get("payee_id"),
                "amount": t.get("amount"), "transaction_date": t.get("transaction_date"),
                "status": t.get("status"), "medium": t.get("medium") or local_row.get("medium"),
                "description": description, "occurred_at": occurred,
                **extras("transfers", t["_id"], ["payee_name", "label", "scenario"]),
            })
        rows += db.upsert(conn, "transfers", transfers)

    db.rebuild_payees(conn)
    db.set_meta(conn, "as_of", local.as_of.isoformat())
    db.set_meta(conn, "calibration", local.calibration)
    db.set_meta(conn, "scenarios", local.scenarios)
    db.set_meta(conn, "last_nessie_sync", datetime.now().isoformat(timespec="seconds"))

    conn.execute(
        "INSERT INTO sync_runs (started_at, finished_at, source, rows, api_calls, note) "
        "VALUES (?,?,?,?,?,?)",
        (started, datetime.now().isoformat(timespec="seconds"), "nessie", rows,
         client.calls, "poll"),
    )
    conn.commit()
    return db.counts(conn)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill the local cache.")
    parser.add_argument("--source", choices=["local", "nessie"], default="local",
                        help="local: regenerate offline (default). nessie: poll the API.")
    parser.add_argument("--watch", type=int, metavar="SECONDS",
                        help="keep polling every N seconds (Nessie has no webhooks)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    def once():
        if args.source == "nessie":
            return sync_from_nessie(verbose=not args.quiet)
        return load_local(build())

    try:
        counts = once()
    except (NessieError, RuntimeError) as exc:
        print(f"sync failed: {exc}")
        return 1

    print(f"cache ready ({args.source}): " + json.dumps(counts))

    if args.watch:
        import time
        print(f"watching every {args.watch}s, ctrl-c to stop")
        try:
            while True:
                time.sleep(args.watch)
                counts = once()
                print(f"[{datetime.now():%H:%M:%S}] " + json.dumps(counts))
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
