"""Write the shared JSON fixtures under mocks/.

Two kinds of file:

  dataset.json, <persona>_snapshot.json
      Real generated data. P2 builds the engine against these before the database
      exists.

  api_*.json
      Responses shaped exactly like the endpoint contract in begin.md section 7,
      so P4 can build every screen before P3's backend answers anything.

Numbers in the api_* files come from P1's own reference projection. At runtime
P2's engine is the source of truth -- if the two ever disagree, that disagreement
is a bug worth finding before the demo, which is exactly why we publish ours.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from backend.nessie import config, db, repo
from seed.generator import Dataset, build, iso, money, project


def _write(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")
    return path


def build_api_mocks(ds: Dataset, conn) -> dict[str, dict]:
    out: dict[str, dict] = {}
    as_of = ds.as_of

    for key, cal in ds.calibration.items():
        snap = repo.snapshot(conn, key)
        if not snap:
            continue
        person = snap["customer"]
        flight = date.fromisoformat(cal["flight_home"])
        events = [(date.fromisoformat(e["date"]), e["amount"]) for e in cal["future_events"]]
        horizon = max(flight, date.fromisoformat(cal["runway_target"]))
        proj = project(cal["checking_balance"], as_of, horizon,
                       cal["daily_discretionary"], events, cal["safety_buffer"])

        accounts = [
            {"id": a["id"], "type": a["type"], "nickname": a["nickname"],
             "balance": a["balance"],
             **({"limit": a["credit_limit"], "utilization": round(a["balance"] / a["credit_limit"], 4)}
                if a.get("credit_limit") else {})}
            for a in snap["accounts"]
        ]

        out[f"api_users_{key}_summary"] = {
            "_source": "P1 reference projection",
            "user": key,
            "name": f"{person['first_name']} {person['last_name']}",
            "accounts": accounts,
            "as_of": iso(as_of),
            "runway_date": cal["runway_date"],
            "target_date": cal["flight_home"],
            "gap": cal["gap"],
            "safety_buffer": cal["safety_buffer"],
            "daily_burn": cal["daily_discretionary"],
            "currency": "USD",
            "home_currency": person["home_currency"],
            "fx_rate": person["fx_rate"],
            "_simulated": ["limit", "utilization", "fx_rate"],
        }

        out[f"api_users_{key}_forecast"] = {
            "_source": "P1 reference projection",
            "user": key,
            "target": cal["flight_home"],
            "runway_date": cal["runway_date"],
            "gap": cal["gap"],
            "min_balance": cal["min_balance"],
            "min_balance_date": cal["min_balance_date"],
            "daily_burn": cal["daily_discretionary"],
            "series": proj.series,
            "events": [
                {"date": e["date"], "amount": e["amount"],
                 "label": _event_label(ds, key, e["date"], e["amount"])}
                for e in cal["future_events"]
            ],
        }

        out[f"api_users_{key}_bills"] = {
            "user": key,
            "bills": [
                {"id": b["id"], "nickname": b["nickname"], "payee": b["payee"],
                 "amount": b["payment_amount"], "next_date": b["upcoming_payment_date"],
                 "recurring_day": b["recurring_date"], "category": b["category"],
                 "explanation": b["explanation"],
                 **({"heads_up": f"Free trial ends {b['trial_converts_on']}, "
                                 f"then {b['trial_amount_after']:.2f}/month"}
                    if b["is_trial"] else {})}
                for b in snap.get("bills", [])
            ],
        }

        if snap.get("credit"):
            credit = snap["credit"]
            limit = credit["limit"]
            out[f"api_users_{key}_credit"] = {
                "user": key,
                "balance": credit["balance"],
                "limit": limit,
                "utilization": credit["utilization"],
                "apr": credit["apr"],
                "statement_day": credit["statement_day"],
                "suggested_payment": money(max(0.0, credit["balance"] - limit * 0.3)),
                "tip": (
                    f"You are using {credit['utilization']:.0%} of your limit. Paying it down "
                    f"below 30% (about {money(limit * 0.3):.2f}) is what US credit scoring rewards."
                    if credit["utilization"] > 0.3 else
                    "Your utilization is already in the range US credit scoring rewards."
                ),
                "_simulated": ["limit", "apr", "utilization", "suggested_payment", "tip"],
                "_note": "Nessie has no credit limit or credit score. These are ours and the pitch says so.",
            }

    # The risk families -- api_transfers_check_*.json and api_users_*_alerts.json --
    # used to be stubbed here so P3 and P4 had a shape to build against before P2
    # existed. P2's engine now computes them for real, from this cache, and a reset
    # was quietly overwriting live engine output (a scored 84 with real reasons) with
    # our illustrative placeholders. They are P2's to write; we do not touch them.
    #
    # Refresh them with: python -m backend.engine.export

    out["api_chat_response_if_missing"] = {
        "_owner": "P3 produces this at runtime; shape only",
        "reply": "Sí, puedes ir, pero solo si te gastas menos de 250 $. El alquiler "
                 "de 950 $ sale el 1 de octubre y te quedarías con 180 $ de margen.",
        "language": "es",
        "used_tools": ["get_summary", "check_affordability"],
        "proposed_action": {
            "id": "act_123",
            "type": "transfer",
            "from": "savings",
            "to": "checking",
            "amount": 300,
            "effect": {"runway_date_before": "2026-10-10", "runway_date_after": "2026-10-27"},
        },
    }
    return out


def _event_label(ds: Dataset, persona: str, when: str, amount: float) -> str:
    for bill in ds.bills:
        if not bill["account_local_id"].startswith(f"acc_{persona}"):
            continue
        if bill["recurring_date"] == int(when[8:10]) and abs(bill["payment_amount"] + amount) < 0.02:
            return bill["nickname"]
    return "Income" if amount > 0 else "Scheduled payment"


def main() -> int:
    ds = build()
    conn = db.connect()
    db.init(conn)

    written: list[str] = []
    written.append(str(_write(config.MOCKS_DIR / "dataset.json", ds.to_json())))
    written.append(str(_write(config.MOCKS_DIR / "calibration.json", ds.calibration)))
    written.append(str(_write(config.MOCKS_DIR / "scenarios.json", ds.scenarios)))

    for persona in ds.calibration:
        snap = repo.snapshot(conn, persona)
        if snap:
            written.append(str(_write(config.MOCKS_DIR / f"{persona}_snapshot.json", snap)))

    for name, payload in build_api_mocks(ds, conn).items():
        # A "_if_missing" fixture belongs to another layer: seed it so nobody is ever
        # without a fixture, but never overwrite what its real owner has produced.
        if name.endswith("_if_missing"):
            target = config.MOCKS_DIR / f"{name[: -len('_if_missing')]}.json"
            if target.exists():
                continue
            written.append(str(_write(target, payload)))
            continue
        written.append(str(_write(config.MOCKS_DIR / f"{name}.json", payload)))

    index = {
        "generated_at": ds.to_json()["generated_at"],
        "as_of": iso(ds.as_of),
        "files": sorted(Path(f).name for f in written),
        "how_to_use": {
            "P2": "dataset.json and <persona>_snapshot.json are real data. "
                  "calibration.json holds the forecast numbers your engine should reproduce.",
            "P3": "api_*.json fix the response shapes for every endpoint in the contract.",
            "P4": "api_*.json are drop-in fixtures for every screen.",
        },
    }
    _write(config.MOCKS_DIR / "index.json", index)

    print(f"wrote {len(written) + 1} files to {config.MOCKS_DIR}")
    for name in index["files"]:
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
