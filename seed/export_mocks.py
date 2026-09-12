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

    # Risk responses are P2's to compute. These fix the response *shape* so P3 and
    # P4 can build the pause modal now; the scores are illustrative.
    for scenario in ds.scenarios:
        if scenario["kind"] != "transfer":
            continue
        paused = scenario["expect"] == "pause"
        out[f"api_transfers_check_{scenario['key']}"] = {
            "_owner": "P2 computes this at runtime; shape only",
            "scenario": scenario["key"],
            "amount": scenario["amount"],
            "risk_score": 87 if paused else 6,
            "pause": paused,
            "reasons": (
                ["You have never sent money to this payee",
                 "This is 46% of your checking balance",
                 "Round amount",
                 "The message uses urgent, threatening language"]
                if paused else
                ["You have paid this payee 3 times before", "Usual amount"]
            ),
            "questions": (
                ["Did someone contact you and ask you to pay urgently?",
                 "Have you met or verified this person or company in real life?",
                 "Were you asked to keep this payment private?"]
                if paused else []
            ),
        }

    out["api_users_ana_alerts"] = {
        "_owner": "P2 computes this at runtime; shape only",
        "user": "ana",
        "alerts": [
            {"id": "alert_1", "type": "scam_transfer", "severity": "high",
             "title": "Transfer paused", "amount": 800.0,
             "reason": "New payee, 46% of your balance, urgent wording",
             "created_at": f"{iso(as_of)}T14:05", "status": "open"},
            {"id": "alert_2", "type": "card_anomaly", "severity": "high",
             "title": "Unusual card activity", "amount": 899.0,
             "reason": "5 small charges at new merchants, then a purchase above your credit limit",
             "created_at": f"{iso(as_of)}T14:46", "status": "open"},
        ],
    }

    out["api_chat_response"] = {
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
