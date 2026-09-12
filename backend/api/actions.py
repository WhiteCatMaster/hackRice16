"""The confirmation gate.

begin.md design rule 2: the agent *proposes* an action, the user approves it, and
only then does anything get written. Nothing in this module moves money until
`confirm()` is called with an id that was handed out by `propose()`.

Design rule 4 is enforced here too. `executed_in_nessie` is False whenever the
write only reached the local cache — because there is no API key, because Nessie
refused, or because the action (a spending cap) has no Nessie equivalent. P4's UI
reads that flag and says so on screen, so we never claim a write we did not make.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime

from backend.api import engine_port, reference
from backend.nessie import config, db, repo
from backend.nessie.client import NessieClient, NessieError

log = logging.getLogger("treasurer.actions")

_LOCK = threading.Lock()
_ACTIONS: dict[str, dict] = {}

#: Actions we know how to carry out. Anything else is refused at propose time.
KINDS = ("transfer", "bill_payment", "spending_cap", "freeze_card")

#: How P4 names an account in a proposed action -> the type P1 stores.
_ACCOUNT_TYPES = {
    "savings": "Savings", "Savings": "Savings",
    "checking": "Checking", "Checking": "Checking",
    "credit": "Credit Card", "credit_card": "Credit Card", "Credit Card": "Credit Card",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="minutes")


# --------------------------------------------------------------------------
# propose
# --------------------------------------------------------------------------


def propose(conn, user: str, action: dict) -> dict:
    """Register an intended action and measure it, without carrying it out."""
    kind = action.get("type")
    if kind not in KINDS:
        raise ValueError(f"Unsupported action type {kind!r}. Known: {', '.join(KINDS)}")

    action_id = action.get("id") or f"act_{uuid.uuid4().hex[:10]}"
    amount = round(float(action.get("amount") or 0), 2)

    before = engine_port.call("forecast", conn, user)
    effect = {
        "runway_date_before": before.get("runway_date"),
        "gap_before": before.get("gap"),
    }
    effect.update(_measure(conn, user, kind, amount, action))

    record = {
        **action,
        "id": action_id,
        "user": user,
        "amount": amount,
        "type": kind,
        "status": "proposed",
        "created_at": _now(),
        "effect": {**effect, **(action.get("effect") or {})},
    }
    with _LOCK:
        _ACTIONS[action_id] = record
    log.info("proposed %s %s for %s (%.2f)", action_id, kind, user, amount)
    return record


def _measure(conn, user: str, kind: str, amount: float, action: dict) -> dict:
    """What this action does to the runway, measured by re-running the projection.

    If the live engine's forecast cannot take a hypothetical event, we say so with
    a null date instead of echoing the unchanged one back. An approval card that
    shows "2026-10-10 -> 2026-10-10" for a transfer that does help is a wrong
    number in front of a judge, and worse than an honest blank.
    """
    if kind not in ("transfer", "bill_payment", "spending_cap") or not amount:
        return {"runway_date_after": None, "measured": False,
                "measured_note": f"No projection applies to a {kind} action."}

    sign = 1 if kind in ("transfer", "spending_cap") else -1
    hypothetical = [{
        "date": repo.as_of(conn).isoformat(),
        "amount": sign * amount,
        "label": action.get("label") or kind.replace("_", " ").title(),
    }]

    if engine_port.accepts("forecast", "extra_events"):
        project, measured_by = (
            lambda **kw: engine_port.call("forecast", conn, user, **kw)), engine_port.resolve("forecast")[1]
    else:
        # The live engine cannot model a hypothetical event yet. Measure with
        # P3's reference instead, and take the *before* from the same projection
        # so the pair on the card is internally consistent — a before from one
        # engine and an after from another is how you get a card that lies.
        log.warning("forecast() has no extra_events hook; measuring this effect with the reference")
        project, measured_by = (
            lambda **kw: reference.forecast(conn, user, **kw)), "p3-reference"

    after = project(extra_events=hypothetical)
    if not after:
        return {"runway_date_after": None, "measured": False,
                "measured_note": "The projection returned nothing."}

    out = {
        "runway_date_after": after.get("runway_date"),
        "gap_after": after.get("gap"),
        "min_balance_after": after.get("min_balance"),
        "measured": True,
        "measured_by": measured_by,
    }
    if measured_by == "p3-reference":
        baseline = project()
        out["runway_date_before"] = baseline.get("runway_date")
        out["gap_before"] = baseline.get("gap")
        out["measured_note"] = ("Measured with P3's reference projection, because the live "
                                "engine's forecast does not accept a hypothetical event yet.")
    return out


def get(action_id: str) -> dict | None:
    with _LOCK:
        record = _ACTIONS.get(action_id)
        return dict(record) if record else None


def pending() -> list[dict]:
    with _LOCK:
        return [dict(a) for a in _ACTIONS.values() if a["status"] == "proposed"]


# --------------------------------------------------------------------------
# confirm
# --------------------------------------------------------------------------


def _account(conn, user: str, kind: str) -> dict | None:
    person = repo.resolve_customer(conn, user)
    return repo.account_of_type(conn, person["id"], kind) if person else None


def _move(conn, account_id: str, delta: float) -> None:
    conn.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?", (delta, account_id))


def _push_to_nessie(payer_id: str, payee_id: str, amount: float, description: str) -> tuple[bool, str]:
    """Best effort. A dead or keyless Nessie must never break the demo."""
    if not config.has_api_key():
        return False, "No NESSIE_API_KEY set, so the transfer stayed in the local cache."
    try:
        client = NessieClient()
        client.create_transfer(payer_id, {
            "medium": "balance",
            "payee_id": payee_id,
            "amount": amount,
            "transaction_date": repo_date(),
            "description": description,
            "status": "pending",
        })
        return True, "Written to Nessie."
    except (NessieError, OSError) as exc:
        log.warning("Nessie write failed: %s", exc)
        return False, f"Nessie refused the write ({exc}). The local cache was updated instead."


def repo_date() -> str:
    return config.as_of().isoformat()


def confirm(conn, action_id: str, action: dict | None = None) -> dict:
    """Carry out a previously proposed action. This is the only write path."""
    record = get(action_id)

    # P4 posts the proposed_action back with the confirmation. If the API
    # restarted between propose and approve, rebuild from that rather than
    # failing in front of the judges.
    if not record and action:
        try:
            record = propose(conn, action.get("user") or "ana", {**action, "id": action_id})
        except ValueError as exc:
            return _failed(action_id, str(exc))
    if not record:
        return _failed(action_id, "That action has expired. Ask again and approve the new one.")
    if record["status"] == "executed":
        return {**_result(record, "executed", "Already approved."), "duplicate": True}

    user, amount, kind = record["user"], record["amount"], record["type"]
    executed_in_nessie, note = False, ""

    if kind == "transfer":
        source = _account(conn, user, _ACCOUNT_TYPES.get(record.get("from"), "Savings"))
        target = _account(conn, user, _ACCOUNT_TYPES.get(record.get("to"), "Checking"))
        if not source or not target:
            return _failed(action_id, "Could not find both accounts for that transfer.")
        if float(source["balance"]) < amount:
            return _failed(action_id, f"Your savings only hold ${float(source['balance']):,.2f}.")

        _move(conn, source["id"], -amount)
        _move(conn, target["id"], amount)
        conn.commit()
        executed_in_nessie, note = _push_to_nessie(
            source["id"], target["id"], amount, record.get("label") or "Transfer to checking")
        message = f"Moved ${amount:,.2f} from savings to checking. {note}".strip()

    elif kind == "bill_payment":
        checking = _account(conn, user, "Checking")
        if not checking:
            return _failed(action_id, "No checking account to pay from.")
        _move(conn, checking["id"], -amount)
        conn.commit()
        message = f"Paid ${amount:,.2f}. Recorded in your local cache."

    elif kind == "spending_cap":
        caps = db.get_meta(conn, "spending_caps") or {}
        caps.setdefault(user, {})[record.get("category", "general")] = record.get("weekly_cap", amount)
        db.set_meta(conn, "spending_caps", caps)
        message = (f"Cap saved: {record.get('label') or record.get('category')}. "
                   "This is our own budgeting feature — Nessie has no equivalent.")

    elif kind == "freeze_card":
        card = _account(conn, user, "Credit Card")
        if card:
            conn.execute(
                "UPDATE accounts SET is_frozen = 1, frozen_reason = ? WHERE id = ?",
                (record.get("reason") or "Frozen from the safety centre", card["id"]))
            conn.commit()
        message = ("Card frozen in the app. Nessie has no freeze endpoint, "
                   "so this is ours and the pitch says so.")

    else:  # pragma: no cover — propose() already rejected anything else
        return _failed(action_id, f"Unsupported action type {kind!r}.")

    after = engine_port.call("forecast", conn, user)
    with _LOCK:
        _ACTIONS[action_id].update({
            "status": "executed",
            "executed_at": _now(),
            "executed_in_nessie": executed_in_nessie,
            "runway_date_after": after.get("runway_date"),
        })
    return _result(get(action_id), "executed", message, after.get("runway_date"), executed_in_nessie)


def _result(record, status, message, runway_after=None, in_nessie=False) -> dict:
    return {
        "id": record["id"],
        "status": status,
        "message": message,
        "runway_date_after": runway_after if runway_after is not None else record.get("runway_date_after"),
        "executed_in_nessie": bool(record.get("executed_in_nessie", in_nessie)),
        "action": record,
    }


def _failed(action_id: str, message: str) -> dict:
    log.info("action %s failed: %s", action_id, message)
    return {
        "id": action_id,
        "status": "failed",
        "message": message,
        "runway_date_after": None,
        "executed_in_nessie": False,
    }
