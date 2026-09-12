"""Fire a scam or anomaly scenario on demand.

These deliberately do not exist in the seeded history: "you have never paid this
payee" and "you have never used this merchant" are only true because of that. So
they live here and get injected when the demo needs them.

    python -m seed.scenarios --list
    python -m seed.scenarios card_testing          # inject into the cache
    python -m seed.scenarios card_testing --push   # and into Nessie
    python -m seed.scenarios --clear               # undo every injected scenario

A transfer scenario is NOT executed. It is staged as a pending transfer for the
engine to score, because the whole point is stopping it before the money leaves.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime

from backend.nessie import db
from backend.nessie.client import NessieClient, NessieError
from backend.nessie.timestamps import encode
from seed.generator import build


def list_scenarios(ds) -> str:
    lines = []
    for s in ds.scenarios:
        expect = {"pause": "should PAUSE", "alert": "should ALERT", "allow": "should ALLOW"}[s["expect"]]
        lines.append(f"  {s['key']:<20} {s['title']:<36} {expect}\n      {s['why']}")
    return "\n".join(lines)


def inject(key: str, conn, push: bool = False, verbose: bool = True) -> dict:
    ds = build()
    scenario = next((s for s in ds.scenarios if s["key"] == key), None)
    if scenario is None:
        raise KeyError(key)

    mapping = {r["local_id"]: r["nessie_id"] for r in conn.execute("SELECT local_id, nessie_id FROM id_map")}
    resolve = lambda local: mapping.get(local, local)
    client = NessieClient() if push else None
    if push and not mapping:
        raise RuntimeError("nothing has been pushed to Nessie yet; run `python -m seed.seed --push` first")

    written = {"scenario": key, "rows": 0, "pushed": 0}

    if scenario["kind"] == "transfer":
        # Staged as pending on purpose: the demo is about stopping it, not sending it.
        local_id = f"scn_{key}"
        row = {
            "id": resolve(local_id), "local_id": local_id,
            "payer_id": resolve(scenario["payer_local_id"]),
            "payee_id": resolve(scenario["payee_local_id"]),
            "amount": scenario["amount"],
            "transaction_date": scenario["transaction_date"],
            "occurred_at": scenario["occurred_at"],
            "status": "pending",
            "medium": "balance",
            "description": scenario["description"],
            "payee_name": _payee_name(conn, resolve(scenario["payee_local_id"])),
            "label": scenario["label"],
            "scenario": key,
        }
        written["rows"] += db.upsert(conn, "transfers", [row])
        if push:
            try:
                nessie_id = client.create_transfer(row["payer_id"], {
                    "medium": "balance", "payee_id": row["payee_id"], "amount": row["amount"],
                    "transaction_date": row["transaction_date"], "status": "pending",
                    "description": encode(row["description"], row["occurred_at"]),
                })
                conn.execute("INSERT OR REPLACE INTO id_map (entity, local_id, nessie_id) VALUES (?,?,?)",
                             ("transfer", local_id, nessie_id))
                written["pushed"] += 1
            except NessieError as exc:
                written["push_error"] = str(exc)
    else:
        rows = []
        for i, item in enumerate(scenario["purchases"]):
            local_id = f"scn_{key}_{i}"
            rows.append({
                "id": resolve(local_id), "local_id": local_id,
                "account_id": resolve(item["account_local_id"]),
                "merchant_id": resolve(item["merchant_local_id"]),
                "amount": item["amount"], "purchase_date": item["purchase_date"],
                "occurred_at": item["occurred_at"], "status": item["status"],
                "medium": item["medium"],
                "description": _merchant_name(conn, resolve(item["merchant_local_id"])),
                "label": "fraud", "scenario": key,
            })
        written["rows"] += db.upsert(conn, "purchases", rows)
        if push:
            for row in rows:
                try:
                    nessie_id = client.create_purchase(row["account_id"], {
                        "merchant_id": row["merchant_id"], "medium": row["medium"],
                        "purchase_date": row["purchase_date"], "amount": row["amount"],
                        "status": row["status"],
                        "description": encode(row["description"], row["occurred_at"]),
                    })
                    conn.execute("INSERT OR REPLACE INTO id_map (entity, local_id, nessie_id) VALUES (?,?,?)",
                                 ("purchase", row["local_id"], nessie_id))
                    written["pushed"] += 1
                except NessieError as exc:
                    written["push_error"] = str(exc)
                    break

    db.rebuild_payees(conn)
    db.set_meta(conn, f"scenario_{key}_fired_at", datetime.now().isoformat(timespec="seconds"))
    conn.commit()
    if verbose:
        print(f"{scenario['title']}: {written['rows']} rows into the cache"
              + (f", {written['pushed']} into Nessie" if push else ""))
        print(f"  expected outcome: {scenario['expect'].upper()} -- {scenario['why']}")
    return written


def clear(conn, verbose: bool = True) -> int:
    removed = conn.execute("DELETE FROM purchases WHERE scenario IS NOT NULL").rowcount
    removed += conn.execute("DELETE FROM transfers WHERE scenario IS NOT NULL").rowcount
    conn.commit()
    db.rebuild_payees(conn)
    if verbose:
        print(f"removed {removed} injected scenario rows from the cache")
    return removed


def _payee_name(conn, account_id: str) -> str:
    row = conn.execute(
        "SELECT c.first_name, c.last_name FROM accounts a "
        "JOIN customers c ON c.id = a.customer_id WHERE a.id=?", (account_id,)
    ).fetchone()
    return f"{row['first_name']} {row['last_name']}" if row else "Unknown payee"


def _merchant_name(conn, merchant_id: str) -> str:
    row = conn.execute("SELECT name FROM merchants WHERE id=?", (merchant_id,)).fetchone()
    return row["name"] if row else "Unknown merchant"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fire a scam or anomaly scenario.")
    parser.add_argument("key", nargs="?", help="scenario key, or 'all'")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--clear", action="store_true", help="remove every injected scenario")
    parser.add_argument("--push", action="store_true", help="also write it to Nessie")
    args = parser.parse_args()

    ds = build()
    if args.list or (not args.key and not args.clear):
        print("scenarios:\n" + list_scenarios(ds))
        return 0

    conn = db.connect()
    db.init(conn)

    if args.clear:
        clear(conn)
        return 0

    keys = [s["key"] for s in ds.scenarios] if args.key == "all" else [args.key]
    for key in keys:
        try:
            inject(key, conn, push=args.push)
        except KeyError:
            print(f"unknown scenario '{key}'. Known: {', '.join(s['key'] for s in ds.scenarios)}")
            return 1
        except (NessieError, RuntimeError) as exc:
            print(f"failed: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
