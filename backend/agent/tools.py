"""The agent's tools.

Every tool is a thin wrapper over P2's engine (via `engine_port`) or P1's cache.
None of them return prose, and none of them let the model do arithmetic — that is
the point. The two `propose_*` tools stage an action behind the confirmation
gate; nothing here writes to Nessie.
"""

from __future__ import annotations

from backend.api import actions, engine_port
from backend.nessie import repo

SCHEMA = [
    {
        "name": "get_summary",
        "description": "Balances for every account, the runway date (when checking drops "
                       "below the safety buffer), the flight-home date and the gap.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_forecast",
        "description": "Day-by-day projected checking balance to a target date, plus every "
                       "scheduled bill and expected deposit in between.",
        "input_schema": {
            "type": "object",
            "properties": {"target": {"type": "string", "description": "YYYY-MM-DD. Defaults to the flight home."}},
        },
    },
    {
        "name": "check_affordability",
        "description": "Can they spend this amount? Re-runs the forecast with the expense "
                       "added and reports the new runway date and the safe maximum.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "US dollars."},
                "when": {"type": "string", "description": "YYYY-MM-DD. Defaults to today."},
            },
            "required": ["amount"],
        },
    },
    {
        "name": "get_bills",
        "description": "Recurring bills with amounts, next dates, and a plain-language "
                       "explanation of what each one is. Includes trial-conversion warnings.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_credit",
        "description": "Credit card balance, limit, utilization and the payment that would "
                       "bring utilization under 30%. Limit and utilization are simulated.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_activity",
        "description": "Recent transactions, newest first. Negative amounts are money out.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Default 8."}},
        },
    },
    {
        "name": "get_alerts",
        "description": "Open scam and card-anomaly alerts.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "check_transfer",
        "description": "Risk-check a transfer BEFORE it happens. Returns a score, the reasons "
                       "behind it, and the questions to ask. Call this before helping with any "
                       "payment to someone new.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "payee_name": {"type": "string"},
                "payee_id": {"type": "string"},
                "description": {"type": "string", "description": "What the payer was told this is for."},
            },
            "required": ["amount"],
        },
    },
    {
        "name": "suggest_fixes",
        "description": "Candidate actions that would close the gap, each measured: what the "
                       "runway date becomes if that one fix is taken.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "propose_transfer",
        "description": "Stage a transfer between the user's own accounts for approval. This "
                       "does NOT move money — it puts an approval card on screen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "from": {"type": "string", "enum": ["savings", "checking"]},
                "to": {"type": "string", "enum": ["checking", "savings"]},
                "label": {"type": "string"},
            },
            "required": ["amount"],
        },
    },
    {
        "name": "propose_spending_cap",
        "description": "Stage a weekly spending cap on one category for approval. Our own "
                       "budgeting feature, not a bank product.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "weekly_cap": {"type": "number"},
            },
            "required": ["category", "weekly_cap"],
        },
    },
]

READ_ONLY = {t["name"] for t in SCHEMA if not t["name"].startswith("propose_")}


def run(conn, user: str, name: str, args: dict) -> dict:
    """Dispatch one tool call. Returns whatever the engine returned, as data."""
    args = args or {}

    if name == "get_summary":
        return engine_port.call("summary", conn, user)
    if name == "get_forecast":
        out = engine_port.call("forecast", conn, user, target=args.get("target"))
        # The full day-by-day series is for the chart, not the model's context.
        return {k: v for k, v in out.items() if k != "series"}
    if name == "check_affordability":
        return engine_port.call("affordability", conn, user, float(args["amount"]),
                                when=args.get("when"))
    if name == "get_bills":
        return engine_port.call("bills", conn, user)
    if name == "get_credit":
        return engine_port.call("credit", conn, user)
    if name == "get_activity":
        return engine_port.call("activity", conn, user, limit=int(args.get("limit") or 8))
    if name == "get_alerts":
        return engine_port.call("alerts", conn, user)
    if name == "check_transfer":
        return engine_port.call(
            "check_transfer", conn, user,
            payee_id=args.get("payee_id"), amount=float(args.get("amount") or 0),
            description=args.get("description"), payee_name=args.get("payee_name"))
    if name == "suggest_fixes":
        return {"fixes": engine_port.call("suggest_fixes", conn, user)}

    if name == "propose_transfer":
        return actions.propose(conn, user, {
            "type": "transfer",
            "from": args.get("from") or "savings",
            "to": args.get("to") or "checking",
            "amount": float(args["amount"]),
            "label": args.get("label") or "Transfer from savings",
        })
    if name == "propose_spending_cap":
        weekly = float(args["weekly_cap"])
        category = args["category"]
        snap = repo.snapshot(conn, user)
        spent_month = float((snap.get("category_spend_30d") or {}).get(category, 0.0))
        saved = max(0.0, (spent_month / 4.0) - weekly)
        return actions.propose(conn, user, {
            "type": "spending_cap",
            "category": category,
            "weekly_cap": weekly,
            "amount": round(saved * 4, 2),
            "label": f"Cap {category} at ${weekly:,.0f} a week",
        })

    return {"error": f"unknown tool {name!r}"}
