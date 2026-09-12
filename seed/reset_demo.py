"""Put the demo back to its starting state, in one command.

    python -m seed.reset_demo            # local cache only, ~1 second
    python -m seed.reset_demo --arm      # ...and fire every scenario
    python -m seed.reset_demo --push     # also re-seed Nessie

Run this before every rehearsal and immediately before going on stage. It wipes
injected scenarios, regenerates the dataset, reloads the cache and refreshes the
mocks, so the runway chart and every number look exactly like they did in
rehearsal.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date

from backend.nessie import db
from backend.nessie.client import NessieClient, NessieError
from seed.export_mocks import main as export_mocks
from seed.generator import build
from seed.validate import validate


def delete_seeded_from_nessie(conn, client: NessieClient, verbose: bool = True) -> int:
    """Delete only what we created, tracked by id_map.

    Deleting the customers takes their accounts and transactions with them, which
    is why we do not walk every purchase.
    """
    rows = list(conn.execute("SELECT entity, nessie_id FROM id_map WHERE entity IN ('customer','account')"))
    deleted = 0
    for row in rows:
        try:
            if row["entity"] == "customer":
                client.delete_customer(row["nessie_id"])
            else:
                client.delete_account(row["nessie_id"])
            deleted += 1
        except NessieError as exc:
            # A 404 just means it is already gone, which is the state we want.
            if exc.status != 404 and verbose:
                print(f"  could not delete {row['entity']} {row['nessie_id']}: {exc.status}")
    conn.execute("DELETE FROM id_map")
    conn.commit()
    if verbose:
        print(f"  deleted {deleted} objects from Nessie")
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset the demo to its starting state.")
    parser.add_argument("--push", action="store_true", help="also wipe and re-seed Nessie")
    parser.add_argument("--keep-nessie", action="store_true",
                        help="with --push: add to Nessie without deleting the old objects")
    parser.add_argument("--as-of", type=date.fromisoformat, help="override the demo 'today'")
    parser.add_argument("--no-mocks", action="store_true", help="skip refreshing mocks/")
    parser.add_argument("--scenario", action="append", default=[],
                        help="fire a scenario after resetting (repeatable)")
    parser.add_argument("--arm", action="store_true",
                        help="fire every scenario after resetting, so the Safety centre has "
                             "something in it. This is the state mocks/api_users_*_alerts.json "
                             "was exported from, so the live app and the fixtures agree.")
    args = parser.parse_args()

    started = time.time()
    conn = db.connect()
    db.init(conn)

    print("generating dataset...")
    ds = build(as_of=args.as_of)
    result = validate(ds)
    if not result.ok():
        print(result.report())
        print("\nvalidation failed, refusing to reset.")
        return 1
    print(f"  {len(result.results)} consistency checks passed")

    if args.push:
        client = NessieClient(verbose=False)
        reachable, why = client.ping()
        if not reachable:
            print(f"cannot reach Nessie: {why}")
            return 1
        if not args.keep_nessie:
            print("clearing previously seeded objects from Nessie...")
            delete_seeded_from_nessie(conn, client)

    print("wiping the local cache...")
    db.wipe(conn)

    if args.push:
        from seed.seed import push_dataset, reconcile_balances
        from backend.nessie.sync import sync_from_nessie

        client = NessieClient(verbose=False)
        try:
            pusher = push_dataset(ds, client, conn)
        except NessieError as exc:
            print(f"seed failed: {exc}\nRe-run `python -m seed.seed --push --resume`.")
            return 1
        print("reconciling balances...")
        for row in reconcile_balances(ds, client, pusher):
            if "error" not in row and abs(row["delta"]) >= 0.01:
                print(f"  {row['account']}: Nessie {row['nessie']:.2f} -> {row['intended']:.2f}")
        print("pulling back into the cache...")
        counts = sync_from_nessie(conn, client=NessieClient(verbose=False), verbose=False)
    else:
        from backend.nessie.sync import load_local
        counts = load_local(ds, conn)

    if not args.no_mocks:
        print("refreshing mocks...")
        export_mocks()

    scenarios = list(args.scenario)
    if args.arm:
        from backend.nessie import repo
        # Every one of them: a clean cache has no alerts at all, which makes the
        # Safety centre look broken rather than calm. The alerts fixture is
        # exported with all of them fired, so this is also what keeps live mode
        # and mock mode showing the same screen.
        scenarios = [s["key"] for s in repo.scenarios(conn)]
    for key in scenarios:
        from seed.scenarios import inject
        inject(key, conn, push=args.push)

    ana = ds.calibration["ana"]
    elapsed = time.time() - started
    print(f"\nreset complete in {elapsed:.1f}s")
    print(f"  rows: {sum(counts.values())}  ({', '.join(f'{k} {v}' for k, v in counts.items())})")
    print(f"  demo date        {ds.as_of}")
    print(f"  Ana checking     ${ana['checking_balance']:.2f}")
    print(f"  Ana runway       {ana['runway_date']}")
    print(f"  Ana flies home   {ana['flight_home']}")
    print(f"  Ana's gap        ${ana['gap']:.2f}")
    if scenarios:
        print(f"  scenarios armed  {', '.join(scenarios)}")
    else:
        print("  scenarios armed  none -- the Safety centre will be empty. Use --arm.")
    if elapsed > 60:
        print("\n  WARNING: reset took over a minute. Use the local reset before going on stage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
