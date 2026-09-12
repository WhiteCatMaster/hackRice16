"""Route handlers, with no web framework in sight.

Every handler is a plain function that takes the request pieces and returns
`(status, dict)`. `app.py` wraps them in FastAPI; `serve.py` wraps the same
functions in the standard library's HTTP server. That is what lets the backend
still come up on a laptop where `pip install` failed at 3 a.m.
"""

from __future__ import annotations

import logging

from backend.api import actions, engine_port
from backend.nessie import config, db, repo

log = logging.getLogger("landed.api")

PERSONA_FALLBACK = "ana"


def _conn():
    return db.connect()


def _known(conn, user: str) -> bool:
    return repo.resolve_customer(conn, user) is not None


def _missing(user: str):
    return 404, {"error": "unknown_user", "message": f"No persona called {user!r}."}


# --------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------


def health(_conn_=None):
    conn = _conn_ or _conn()
    engine = engine_port.status()
    return 200, {
        "ok": True,
        "service": "landed-api",
        "owner": "P3",
        "as_of": repo.as_of(conn).isoformat(),
        "cache": db.counts(conn),
        "personas": [p["persona_key"] for p in repo.personas(conn)],
        "nessie_key_present": config.has_api_key(),
        "agent": _agent_status(),
        "engine": engine,
    }


def _agent_status() -> dict:
    from backend.agent import loop
    return loop.status()


def summary(user: str):
    conn = _conn()
    if not _known(conn, user):
        return _missing(user)
    return 200, engine_port.call("summary", conn, user)


def forecast(user: str, target: str | None = None):
    conn = _conn()
    if not _known(conn, user):
        return _missing(user)
    return 200, engine_port.call("forecast", conn, user, target=target)


def bills(user: str):
    conn = _conn()
    if not _known(conn, user):
        return _missing(user)
    return 200, engine_port.call("bills", conn, user)


def credit(user: str):
    conn = _conn()
    if not _known(conn, user):
        return _missing(user)
    return 200, engine_port.call("credit", conn, user)


def alerts(user: str):
    conn = _conn()
    if not _known(conn, user):
        return _missing(user)
    return 200, engine_port.call("alerts", conn, user)


def activity(user: str, limit: int = 8):
    conn = _conn()
    if not _known(conn, user):
        return _missing(user)
    return 200, engine_port.call("activity", conn, user, limit=int(limit))


def profile(user: str):
    conn = _conn()
    if not _known(conn, user):
        return _missing(user)
    return 200, engine_port.call("profile", conn, user)


# --------------------------------------------------------------------------
# writes and checks
# --------------------------------------------------------------------------


def affordability(user: str, body: dict):
    conn = _conn()
    if not _known(conn, user):
        return _missing(user)
    try:
        amount = float(body.get("amount"))
    except (TypeError, ValueError):
        return 400, {"error": "bad_amount", "message": "Send a numeric 'amount'."}
    return 200, engine_port.call(
        "affordability", conn, user, amount, when=body.get("when") or body.get("date"))


def transfers_check(body: dict):
    """P4 posts either a scenario key or a raw payee + amount + description."""
    conn = _conn()
    user = body.get("user") or PERSONA_FALLBACK

    payee_id = body.get("payee_id")
    amount = body.get("amount")
    description = body.get("description")
    payee_name = body.get("payee_name")
    scenario_key = body.get("scenario")

    if scenario_key:
        match = next((s for s in repo.scenarios(conn) if s.get("key") == scenario_key), None)
        if not match:
            return 404, {"error": "unknown_scenario", "message": f"No scenario {scenario_key!r}."}
        user = match.get("persona") or user
        payee_id = payee_id or match.get("payee_local_id")
        amount = match.get("amount") if amount is None else amount
        description = description or match.get("description")

    if not _known(conn, user):
        return _missing(user)
    try:
        amount = float(amount or 0)
    except (TypeError, ValueError):
        return 400, {"error": "bad_amount", "message": "Send a numeric 'amount'."}

    result = engine_port.call(
        "check_transfer", conn, user,
        payee_id=payee_id, amount=amount, description=description, payee_name=payee_name)
    if scenario_key:
        result.setdefault("scenario", scenario_key)
    return 200, result


def chat(body: dict):
    from backend.agent import loop

    conn = _conn()
    user = body.get("user") or PERSONA_FALLBACK
    message = (body.get("message") or "").strip()
    if not message:
        return 400, {"error": "empty_message", "message": "Send a 'message'."}
    if not _known(conn, user):
        return _missing(user)
    return 200, loop.answer(conn, user, message, language=body.get("language"))


def confirm(action_id: str, body: dict):
    conn = _conn()
    action = body.get("action") or {}
    if body.get("user") and not action.get("user"):
        action["user"] = body["user"]
    return 200, actions.confirm(conn, action_id, action or None)


def propose(body: dict):
    """Not in §7. Lets P4 (or a curl) stage an action without going through chat."""
    conn = _conn()
    user = body.get("user") or PERSONA_FALLBACK
    if not _known(conn, user):
        return _missing(user)
    try:
        return 200, actions.propose(conn, user, body.get("action") or body)
    except ValueError as exc:
        return 400, {"error": "bad_action", "message": str(exc)}


def fixes(user: str):
    conn = _conn()
    if not _known(conn, user):
        return _missing(user)
    return 200, {"user": user, "fixes": engine_port.call("suggest_fixes", conn, user)}


def scenarios(_body=None):
    conn = _conn()
    return 200, {"scenarios": repo.scenarios(conn)}
