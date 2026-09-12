"""P3's stand-in engine — used only until P2's `backend.engine` lands.

begin.md §7 says P3 "works against stub engine functions returning fixed values
until P2 delivers". Fixed values would give P4 a flat runway chart, so this goes
one step further: it reproduces P1's *published* reference projection from the
cache, using the calibration numbers in `mocks/calibration.json` as the source of
truth for the burn rate.

This is deliberately not a competing engine. P2 owns the real one. Every function
here is shadowed the moment the matching name appears in `backend.engine` — see
`engine_port.py` — and `/api/health` always says which one answered.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from backend.nessie import repo

SAFETY_BUFFER = 100.0


def _money(value) -> str:
    """Negative money reads as -$12.00, never as $-12.00."""
    value = float(value)
    return f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"

# --------------------------------------------------------------------------
# dates
# --------------------------------------------------------------------------


def _d(value) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _add_months(day: date, months: int) -> date:
    """Same day-of-month `months` later, clamped to the length of that month."""
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    for dom in (day.day, 30, 29, 28):
        try:
            return date(year, month, dom)
        except ValueError:
            continue
    raise ValueError(day)


# --------------------------------------------------------------------------
# future events: the bills and deposits between today and the flight home
# --------------------------------------------------------------------------


def _bill_events(bills: list[dict], start: date, target: date) -> list[dict]:
    out = []
    for bill in bills:
        first = _d(bill.get("upcoming_payment_date")) or _d(bill.get("payment_date"))
        amount = float(bill.get("payment_amount") or 0)
        if not first or not amount:
            continue
        when, guard = first, 0
        while when <= target and guard < 40:
            if when >= start:
                out.append({
                    "date": when.isoformat(),
                    "amount": -round(amount, 2),
                    "label": bill.get("nickname") or bill.get("payee") or "Bill",
                })
            when = _add_months(when, 1)
            guard += 1
    return out


def _deposit_events(deposits: list[dict], start: date, target: date) -> list[dict]:
    """Project deposits P1 already flagged as recurring.

    Cadence comes from the median gap between occurrences: ~14 days is a payroll
    run, ~monthly is a stipend. A single sighting is assumed monthly.
    """
    groups: dict[str, list[dict]] = {}
    for dep in deposits:
        if not dep.get("is_recurring"):
            continue
        key = f"{dep.get('description') or 'Deposit'}|{round(float(dep.get('amount') or 0), 2)}"
        groups.setdefault(key, []).append(dep)

    out = []
    for key, items in groups.items():
        items.sort(key=lambda r: str(r.get("transaction_date") or ""))
        days = [_d(r.get("transaction_date")) for r in items]
        days = [d for d in days if d]
        if not days:
            continue
        amount = round(float(items[-1].get("amount") or 0), 2)
        label = items[-1].get("description") or "Deposit"
        last = days[-1]

        gaps = sorted((b - a).days for a, b in zip(days, days[1:]))
        gap = gaps[len(gaps) // 2] if gaps else 30

        when, guard = last, 0
        while guard < 60:
            when = _add_months(when, 1) if gap >= 26 else when + timedelta(days=gap)
            guard += 1
            if when > target:
                break
            if when >= start:
                out.append({"date": when.isoformat(), "amount": amount, "label": label})
    return out


def future_events(conn, user: str, target: date | None = None) -> list[dict]:
    snap = repo.snapshot(conn, user)
    if not snap:
        return []
    start = repo.as_of(conn)
    target = target or _d(snap.get("flight_home_date")) or (start + timedelta(days=60))
    events = _bill_events(snap.get("bills", []), start, target)
    events += _deposit_events(snap.get("deposits", []), start, target)
    events.sort(key=lambda e: (e["date"], e["label"]))
    return events


# --------------------------------------------------------------------------
# the projection (begin.md §6)
# --------------------------------------------------------------------------


def daily_burn(conn, user: str) -> float:
    """Discretionary spend per day. P1's calibrated figure wins; median otherwise."""
    calibrated = repo.expected_forecast(conn, user) or {}
    if calibrated.get("daily_discretionary"):
        return float(calibrated["daily_discretionary"])

    snap = repo.snapshot(conn, user)
    series = sorted((snap.get("daily_spend_30d") or {}).values())
    if not series:
        return 0.0
    mid = len(series) // 2
    return float(series[mid] if len(series) % 2 else (series[mid - 1] + series[mid]) / 2)


def _project(conn, user: str, target=None, extra_events: list[dict] | None = None) -> dict:
    """Step the checking balance forward one day at a time to the flight home."""
    snap = repo.snapshot(conn, user)
    if not snap:
        return {}

    start = repo.as_of(conn)
    target_date = _d(target) or _d(snap.get("flight_home_date")) or (start + timedelta(days=60))
    checking = next((a for a in snap.get("accounts", []) if a["type"] == "Checking"), None)
    balance = float(checking["balance"]) if checking else 0.0
    burn = daily_burn(conn, user)

    events = future_events(conn, user, target_date) + list(extra_events or [])
    events = [e for e in events if start <= _d(e["date"]) <= target_date]
    events.sort(key=lambda e: (e["date"], e["label"]))

    by_day: dict[str, list[dict]] = {}
    for event in events:
        by_day.setdefault(event["date"], []).append(event)

    series, runway_date = [], None
    min_balance, min_balance_date = balance, start.isoformat()

    day = start
    while day <= target_date:
        if day > start:
            balance -= burn
        today = by_day.get(day.isoformat(), [])
        for event in today:
            balance += event["amount"]

        # Round for display only. Rounding the running balance instead drifts by
        # cents over 50 days, which is enough to move the runway date by a day.
        series.append({"date": day.isoformat(), "balance": round(balance, 2), "events": today})
        if balance < min_balance:
            min_balance, min_balance_date = balance, day.isoformat()
        if runway_date is None and balance < SAFETY_BUFFER:
            runway_date = day.isoformat()
        day += timedelta(days=1)

    return {
        "user": user,
        "target": target_date.isoformat(),
        "runway_date": runway_date,
        "gap": round(max(0.0, SAFETY_BUFFER - min_balance), 2),
        "min_balance": round(min_balance, 2),
        "min_balance_date": min_balance_date,
        "daily_burn": round(burn, 4),
        "safety_buffer": SAFETY_BUFFER,
        "series": series,
        "events": events,
    }


def forecast(conn, user: str, target=None, extra_events: list[dict] | None = None) -> dict:
    out = _project(conn, user, target, extra_events)
    if out:
        out["fixes"] = suggest_fixes(conn, user)
        out["_engine"] = "p3-reference"
    return out


# --------------------------------------------------------------------------
# fixes and affordability
# --------------------------------------------------------------------------


def suggest_fixes(conn, user: str) -> list[dict]:
    """Candidate actions that close the gap, each with its effect on the runway.

    P1's handoff is explicit that Ana's gap is tuned so one $300 transfer does
    *not* close it — both fixes together do. So this returns each fix measured on
    its own, and the caller shows the combination.
    """
    base = _project(conn, user)
    if not base or base["gap"] <= 0:
        return []

    snap = repo.snapshot(conn, user)
    fixes: list[dict] = []
    gap = base["gap"]

    savings = next((a for a in snap.get("accounts", []) if a["type"] == "Savings"), None)
    if savings and savings["balance"] > 0:
        amount = min(round(max(gap, 300.0) / 50) * 50, round(float(savings["balance"]), 2))
        after = _project(conn, user, extra_events=[{
            "date": repo.as_of(conn).isoformat(),
            "amount": amount,
            "label": "Transfer from savings",
        }])
        fixes.append({
            "id": "fix_transfer_savings",
            "type": "transfer",
            "label": f"Move ${amount:,.0f} from savings to checking",
            "amount": amount,
            "from": "savings",
            "to": "checking",
            "detail": "Your savings are yours — this moves them where the bills come out.",
            "effect": {
                "runway_date_before": base["runway_date"],
                "runway_date_after": after["runway_date"],
                "gap_after": after["gap"],
                "min_balance_after": after["min_balance"],
            },
        })

    categories = snap.get("category_spend_30d") or {}
    top = max(categories.items(), key=lambda kv: kv[1], default=None)
    if top and top[1] > 0:
        category, spent = top
        weekly_now = spent / 4.0
        cap = round(weekly_now * 0.6 / 5) * 5
        saved_per_day = max(0.0, (weekly_now - cap) / 7.0)
        days = (_d(base["target"]) - repo.as_of(conn)).days
        after = _project(conn, user, extra_events=[{
            "date": (repo.as_of(conn) + timedelta(days=days)).isoformat(),
            "amount": round(saved_per_day * days, 2),
            "label": f"{category} cap",
        }]) if saved_per_day else base
        fixes.append({
            "id": f"fix_cap_{category}",
            "type": "spending_cap",
            "label": f"Cap {category} at ${cap:,.0f} a week",
            "amount": round(saved_per_day * days, 2),
            "category": category,
            "detail": f"You spend about ${weekly_now:,.0f} a week on {category} right now.",
            "effect": {
                "runway_date_before": base["runway_date"],
                "runway_date_after": after["runway_date"],
                "gap_after": after["gap"],
                "min_balance_after": after["min_balance"],
            },
        })
    return fixes


def can_afford(conn, user: str, amount: float, when=None) -> dict:
    """Re-run the projection with a hypothetical expense on top."""
    amount = round(float(amount), 2)
    day = _d(when) or repo.as_of(conn)
    base = _project(conn, user)
    after = _project(conn, user, extra_events=[{
        "date": day.isoformat(), "amount": -amount, "label": "Planned expense",
    }])

    buffer_left = after["min_balance"] - SAFETY_BUFFER
    max_safe = round(max(0.0, base["min_balance"] - SAFETY_BUFFER), 2)
    affordable = after["min_balance"] >= SAFETY_BUFFER

    before, later = _d(base["runway_date"]), _d(after["runway_date"])
    days_lost = (before - later).days if before and later else 0

    return {
        "user": user,
        "amount": amount,
        "when": day.isoformat(),
        "affordable": affordable,
        "runway_date_before": base["runway_date"],
        "runway_date_after": after["runway_date"],
        "days_lost": days_lost,
        "min_balance_after": after["min_balance"],
        "buffer": round(buffer_left, 2),
        "max_safe_amount": max_safe,
        "reason": (
            f"Spending {_money(amount)} leaves you {_money(after['min_balance'])} "
            "at your lowest point."
            if affordable else
            f"Spending {_money(amount)} drops you to {_money(after['min_balance'])}, "
            f"below your {_money(SAFETY_BUFFER)} buffer. {_money(max_safe)} is the safe limit."
        ),
        "_engine": "p3-reference",
    }


def affordability(conn, user: str, amount: float, when=None) -> dict:
    return can_afford(conn, user, amount, when)


# --------------------------------------------------------------------------
# risk (begin.md §6, "How the scam check works")
# --------------------------------------------------------------------------

URGENCY = re.compile(
    r"\b(urgent|urgente|inmediato|immediate|immediately|today|hoy|now|ya|"
    r"fine|multa|penalty|deport|deportation|arrest|detenci|police|polic|"
    r"lawsuit|final notice|last chance|or you lose|gift card|wire transfer|"
    r"do not tell|keep this private|confidential)\b",
    re.IGNORECASE,
)
IMPERSONATION = re.compile(
    r"\b(uscis|irs|immigration|inmigraci|homeland|social security|ssa|"
    r"embassy|embajada|consulate|police department|sheriff|court)\b",
    re.IGNORECASE,
)
PAUSE_AT = 60


def _account_by_ref(conn, ref: str) -> dict | None:
    if not ref:
        return None
    row = conn.execute(
        "SELECT * FROM accounts WHERE id = ? OR local_id = ? LIMIT 1", (ref, ref)
    ).fetchone()
    return dict(row) if row else None


def check_transfer(conn, user: str, payee_id=None, amount: float = 0.0,
                   description=None, payee_name=None, when=None) -> dict:
    """Score a transfer *before* it executes. Returns reasons, not just a number."""
    amount = round(float(amount or 0), 2)
    snap = repo.snapshot(conn, user)
    checking = next((a for a in snap.get("accounts", []) if a["type"] == "Checking"), None)
    balance = float(checking["balance"]) if checking else 0.0
    payer_id = checking["id"] if checking else None

    payee = _account_by_ref(conn, payee_id) if payee_id else None
    payee_key = payee["id"] if payee else payee_id
    known = repo.known_payee(conn, payer_id, payee_key) if (payer_id and payee_key) else None
    text = " ".join(filter(None, [description, payee_name, payee.get("nickname") if payee else None]))

    score, reasons = 0, []

    if not known:
        score += 35
        reasons.append("You have never sent money to this payee")
    else:
        times = known.get("times_paid") or 0
        reasons.append(f"You have paid this payee {times} time{'s' if times != 1 else ''} before")

    if balance > 0:
        share = amount / balance
        if share >= 0.40:
            score += 25
            reasons.append(f"This is {share:.0%} of your checking balance")
        elif share >= 0.25:
            score += 15
            reasons.append(f"This is {share:.0%} of your checking balance")

    if amount >= 100 and amount % 100 == 0:
        score += 12
        reasons.append("Round amount")

    if URGENCY.search(text):
        score += 25
        reasons.append("The message uses urgent or threatening language")

    if IMPERSONATION.search(text):
        score += 20
        reasons.append("The message claims to be a government agency")

    today = repo.as_of(conn).isoformat()
    recent = [t for t in snap.get("transfers", []) if str(t.get("transaction_date"))[:10] == today]
    if len(recent) >= 3:
        score += 10
        reasons.append(f"{len(recent)} transfers already today")

    score = max(0, min(99, score))
    pause = score >= PAUSE_AT

    return {
        "user": user,
        "amount": amount,
        "risk_score": score,
        "pause": pause,
        "reasons": reasons,
        "questions": [
            "Did someone contact you and ask you to pay urgently?",
            "Have you met or verified this person or company in real life?",
            "Were you asked to keep this payment private?",
        ] if pause else [],
        "_engine": "p3-reference",
    }


def detect_anomalies(conn, user: str) -> list[dict]:
    """Alerts from what is actually in the cache, so firing a scenario shows one."""
    snap = repo.snapshot(conn, user)
    out: list[dict] = []

    for transfer in snap.get("transfers", []):
        if transfer.get("label") != "scam":
            continue
        check = check_transfer(
            conn, user,
            payee_id=transfer.get("payee_id"),
            amount=transfer.get("amount") or 0,
            description=transfer.get("description"),
            payee_name=transfer.get("payee_name"),
        )
        out.append({
            "id": f"alert_{transfer.get('local_id') or transfer.get('id')}",
            "type": "scam_transfer",
            "severity": "high" if check["pause"] else "medium",
            "title": "Transfer paused" if check["pause"] else "Transfer flagged",
            "amount": round(float(transfer.get("amount") or 0), 2),
            "reason": ", ".join(check["reasons"][:3]),
            "created_at": transfer.get("occurred_at") or transfer.get("transaction_date"),
            "status": "open",
        })

    fraud: dict[str, list[dict]] = {}
    for purchase in snap.get("purchases", []) + (snap.get("credit", {}).get("purchases") or []):
        if purchase.get("label") == "fraud":
            fraud.setdefault(purchase.get("scenario") or "card_anomaly", []).append(purchase)

    for scenario, items in fraud.items():
        items.sort(key=lambda p: str(p.get("occurred_at") or ""))
        total = round(sum(float(p.get("amount") or 0) for p in items), 2)
        biggest = max(items, key=lambda p: float(p.get("amount") or 0))
        out.append({
            "id": f"alert_{scenario}",
            "type": "impossible_travel" if scenario == "impossible_travel" else "card_anomaly",
            "severity": "high",
            "title": "Unusual card activity",
            "amount": round(float(biggest.get("amount") or 0), 2),
            "reason": (
                f"{len(items)} charges totalling ${total:,.2f} at merchants you have not used before"
            ),
            "created_at": items[-1].get("occurred_at") or items[-1].get("purchase_date"),
            "status": "open",
        })

    out.sort(key=lambda a: str(a.get("created_at") or ""), reverse=True)
    return out


def alerts(conn, user: str) -> dict:
    return {"user": user, "alerts": detect_anomalies(conn, user)}


# --------------------------------------------------------------------------
# contract-shaped reads (begin.md §7 and frontend/lib/contract.ts)
# --------------------------------------------------------------------------


def summary(conn, user: str) -> dict:
    snap = repo.snapshot(conn, user)
    if not snap:
        return {}
    projection = _project(conn, user)
    customer = snap.get("customer", {})

    accounts = []
    for account in snap.get("accounts", []):
        entry = {
            "id": account["id"],
            "type": account["type"],
            "nickname": account.get("nickname"),
            "balance": round(float(account.get("balance") or 0), 2),
        }
        limit = account.get("credit_limit") or 0
        if limit:
            entry["limit"] = round(float(limit), 2)
            entry["utilization"] = round(float(account["balance"]) / float(limit), 4)
        accounts.append(entry)

    return {
        "user": user,
        "name": " ".join(filter(None, [customer.get("first_name"), customer.get("last_name")])),
        "accounts": accounts,
        "as_of": snap.get("as_of"),
        "runway_date": projection.get("runway_date"),
        "target_date": snap.get("flight_home_date"),
        "gap": projection.get("gap", 0.0),
        "safety_buffer": SAFETY_BUFFER,
        "daily_burn": projection.get("daily_burn", 0.0),
        "currency": "USD",
        "home_currency": snap.get("home_currency"),
        "fx_rate": snap.get("fx_rate"),
        "_simulated": ["limit", "utilization", "fx_rate"],
        "_engine": "p3-reference",
    }


def bills(conn, user: str) -> dict:
    snap = repo.snapshot(conn, user)
    out = []
    for bill in snap.get("bills", []):
        entry = {
            "id": bill.get("local_id") or bill.get("id"),
            "nickname": bill.get("nickname"),
            "payee": bill.get("payee"),
            "amount": round(float(bill.get("payment_amount") or 0), 2),
            "next_date": bill.get("upcoming_payment_date"),
            "recurring_day": bill.get("recurring_date"),
            "category": bill.get("category"),
            "explanation": bill.get("explanation"),
        }
        if bill.get("is_trial") and bill.get("trial_converts_on"):
            entry["heads_up"] = (
                f"Free trial ends {bill['trial_converts_on']}, "
                f"then {float(bill.get('trial_amount_after') or 0):.2f}/month"
            )
        out.append(entry)
    out.sort(key=lambda b: str(b.get("next_date") or ""))
    return {"user": user, "bills": out}


def credit(conn, user: str) -> dict:
    snap = repo.snapshot(conn, user)
    card = snap.get("credit")
    if not card:
        return {"user": user, "balance": 0.0, "limit": 0.0, "utilization": 0.0,
                "apr": 0.0, "statement_day": 0, "suggested_payment": 0.0,
                "tip": "No credit card on this account."}

    balance = round(float(card.get("balance") or 0), 2)
    limit = round(float(card.get("limit") or 0), 2)
    utilization = round(balance / limit, 4) if limit else 0.0
    healthy = round(limit * 0.30, 2)
    suggested = round(max(0.0, balance - healthy), 2)

    if utilization > 0.30:
        tip = (f"You are using {utilization:.0%} of your limit. Paying it down below 30% "
               f"(about {healthy:,.2f}) is what US credit scoring rewards.")
    else:
        tip = (f"You are using {utilization:.0%} of your limit, which is the healthy range. "
               "Paying the full statement balance costs you no interest.")

    return {
        "user": user,
        "balance": balance,
        "limit": limit,
        "utilization": utilization,
        "apr": card.get("apr"),
        "statement_day": card.get("statement_day"),
        "suggested_payment": suggested,
        "tip": tip,
        "_simulated": ["limit", "apr", "utilization", "suggested_payment", "tip"],
        "_note": "Nessie has no credit limit or credit score. These are ours and the pitch says so.",
        "_engine": "p3-reference",
    }


def activity(conn, user: str, limit: int = 20) -> dict:
    """Recent movements, newest first. Amounts are signed: negative is money out."""
    snap = repo.snapshot(conn, user)
    items: list[dict] = []

    def add(rows, kind, label_keys, date_key, sign):
        for row in rows or []:
            label = next((row.get(k) for k in label_keys if row.get(k)), kind.title())
            items.append({
                "id": row.get("local_id") or row.get("id"),
                "label": label,
                "category": row.get("category") or kind,
                "occurred_at": row.get("occurred_at") or row.get(date_key),
                "amount": sign * round(abs(float(row.get("amount") or 0)), 2),
                "kind": kind,
            })

    add(snap.get("purchases"), "purchase", ("merchant_name", "description"), "purchase_date", -1)
    add(snap.get("deposits"), "deposit", ("description",), "transaction_date", 1)
    add(snap.get("withdrawals"), "withdrawal", ("description",), "transaction_date", -1)
    add(snap.get("transfers"), "transfer", ("payee_name", "description"), "transaction_date", -1)

    items.sort(key=lambda i: str(i.get("occurred_at") or ""), reverse=True)
    return {"user": user, "items": items[:limit]}


def profile(conn, user: str) -> dict:
    import json as _json

    snap = repo.snapshot(conn, user)
    customer = snap.get("customer")
    if not customer:
        return {}

    address = customer.get("address") or {}
    if isinstance(address, str):
        try:
            address = _json.loads(address)
        except ValueError:
            address = {}

    return {
        "name": " ".join(filter(None, [customer.get("first_name"), customer.get("last_name")])),
        "home_city": customer.get("home_city"),
        "city": address.get("city"),
        "state": address.get("state"),
        "language": customer.get("language"),
        "arrival_date": customer.get("arrival_date"),
        "flight_home_date": customer.get("flight_home_date"),
    }
