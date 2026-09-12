"""Build the whole demo dataset deterministically, offline.

Nothing here touches the network. `seed.py` pushes the result to Nessie and
`export_mocks.py` dumps it as JSON, so P2/P3/P4 are never blocked on the API.

The interesting part is `calibrate()`. A random-looking pile of transactions makes
a bad demo: the runway either clears the flight home (no story) or collapses
immediately (not believable). So we solve numerically for the two free knobs --
starting checking balance and daily discretionary spend -- until the forecast
lands exactly where the demo script needs it:

    runway date  = flight home - 21 days
    gap          = $410, i.e. a single $300 transfer does NOT quite close it

The projection used to calibrate is the same one specified for P2's engine
(section 6 of begin.md), so their forecast should reproduce these numbers.
"""
from __future__ import annotations

import calendar
import json
import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from backend.nessie import config

SEED_DIR = Path(__file__).resolve().parent

# Merchants tagged like this are reserved for the scam/anomaly scenarios. Keeping
# them out of normal history is what makes "you have never used this merchant"
# and "you have never paid this payee" true when the demo fires.
RESERVED_TAGS = {"card_testing", "far_from_home", "gift_cards", "money_transfer", "high_value"}

# Where inside the crossing day the balance should land, as a fraction of that
# day's total drop. 0.5 is the midpoint.
#
# The runway date is only meaningful if every reasonable estimator agrees on it. We
# originally aimed a single cent under the safety buffer, which made it knife-edge:
# P2's engine measures the burn rate from the transactions rather than from the knob
# our solver found, and seven cents over fifty days moved the date by a day.
#
# The margin has to be expressed against the crossing day's own drop, not against a
# flat number of days' spend. A fixed margin larger than that day's drop pushes the
# crossing *earlier* than the target date -- which is exactly what happened at the
# anchors where the target day had no bill on it.
MARGIN_FRACTION = 0.5


# --------------------------------------------------------------------- dates

def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def end_of_month(d: date, months_ahead: int = 0) -> date:
    base = add_months(d.replace(day=1), months_ahead)
    return base.replace(day=calendar.monthrange(base.year, base.month)[1])


def monthly_occurrences(day: int, start: date, end: date) -> list[date]:
    """Every `day`-of-month between start and end inclusive, clamped to short months."""
    out: list[date] = []
    cursor = start.replace(day=1)
    while cursor <= end:
        last = calendar.monthrange(cursor.year, cursor.month)[1]
        candidate = cursor.replace(day=min(day, last))
        if start <= candidate <= end:
            out.append(candidate)
        cursor = add_months(cursor, 1)
    return out


def every_n_days(start: date, end: date, step: int) -> list[date]:
    out, cursor = [], start
    while cursor <= end:
        out.append(cursor)
        cursor += timedelta(days=step)
    return out


def iso(d: date) -> str:
    return d.isoformat()


def money(x: float) -> float:
    return round(x + 1e-9, 2)


# ----------------------------------------------------------------- projection

@dataclass
class Projection:
    series: list[dict]
    runway_date: date | None
    min_balance: float
    min_balance_date: date | None
    gap: float


def project(
    start_balance: float,
    start_date: date,
    end_date: date,
    daily_burn: float,
    events: list[tuple[date, float]],
    buffer: float,
) -> Projection:
    """Day-by-day balance projection. Mirrors the engine spec in begin.md section 6.

    events: (date, signed amount) -- bills negative, expected deposits positive.
    """
    by_day: dict[date, float] = {}
    detail: dict[date, list[float]] = {}
    for when, delta in events:
        if start_date < when <= end_date:
            by_day[when] = by_day.get(when, 0.0) + delta
            detail.setdefault(when, []).append(money(delta))

    balance = start_balance
    series: list[dict] = [{"date": iso(start_date), "balance": money(balance), "events": []}]
    runway: date | None = None
    lowest, lowest_on = balance, start_date

    cursor = start_date + timedelta(days=1)
    while cursor <= end_date:
        balance -= daily_burn
        delta = by_day.get(cursor, 0.0)
        balance += delta
        series.append({"date": iso(cursor), "balance": money(balance),
                       "events": detail.get(cursor, [])})
        if balance < lowest:
            lowest, lowest_on = balance, cursor
        if runway is None and balance < buffer:
            runway = cursor
        cursor += timedelta(days=1)

    return Projection(series, runway, money(lowest), lowest_on, money(max(0.0, buffer - lowest)))


# ---------------------------------------------------------------- calibration

def _bisect(fn, lo: float, hi: float, target: float, tol: float = 0.01, steps: int = 80) -> float:
    """Find x in [lo, hi] with fn(x) ~= target. fn must be monotonic increasing."""
    for _ in range(steps):
        mid = (lo + hi) / 2
        value = fn(mid)
        if abs(value - target) <= tol:
            return mid
        if value < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def calibrate(
    cal: dict,
    as_of: date,
    flight: date,
    buffer: float,
    future_events: list[tuple[date, float]],
    persona_key: str = "?",
) -> dict:
    """Solve for the knobs listed in `solve_for` so the forecast hits the demo targets.

    Three modes:
      []                                  -> both knobs pinned, just project
      ["daily_discretionary"]             -> balance pinned, solve the burn rate
      ["checking_balance", "daily_..."]   -> solve both from a runway date + gap target

    Solving only works when the persona actually runs short. A persona whose income
    covers their outflow has no shortfall to solve for, so pin both knobs instead --
    we raise rather than silently emit a negative balance.
    """
    runway_target = flight - timedelta(days=int(cal.get("target_runway_days_before_flight", 21)))
    horizon_end = max(flight, runway_target)
    solve_for = set(cal.get("solve_for", []))

    def outflow_between(lo: date, hi: date) -> float:
        return -sum(delta for when, delta in future_events if lo < when <= hi)

    if "checking_balance" in solve_for:
        # With the balance pinned to hit `buffer` exactly on the runway date, the
        # remaining shortfall is a clean increasing function of the burn rate.
        def balance_for(d: float) -> float:
            days = (runway_target - as_of).days
            # Aim for the MIDDLE of the crossing day, not either edge.
            #
            # Landing exactly on the buffer leaves "balance < buffer" false and slips
            # the runway a day. Landing a single cent under -- what we did first --
            # is worse, because it is knife-edge: P2's engine measures the burn rate
            # from the transactions while our generator solved for a knob, and seven
            # cents over fifty days flipped the date.
            #
            # The day's whole drop is the burn plus any bill due that day, so half of
            # that is the midpoint, and the date then survives an estimator being
            # wrong in either direction by up to half a day's outflow.
            # The room available inside the crossing day is that day's whole drop:
            # the burn plus any bill due on it. Half of that is the midpoint, and it
            # keeps the crossing on the target date at every anchor.
            drop = d + outflow_between(runway_target - timedelta(days=1), runway_target)
            return buffer - drop * MARGIN_FRACTION + d * days \
                + outflow_between(as_of, runway_target)

        def gap_for(d: float) -> float:
            return project(balance_for(d), as_of, horizon_end, d, future_events, buffer).gap

        burn = _bisect(gap_for, 0.05, 400.0, float(cal["target_gap"]))
        balance = balance_for(burn)
    elif "daily_discretionary" in solve_for:
        balance = float(cal["checking_balance"])

        # Balance on the target date falls as the burn rate rises, so negate to
        # keep _bisect's monotonic-increasing contract.
        def deficit_for(d: float) -> float:
            proj = project(balance, as_of, horizon_end, d, future_events, buffer)
            drop = d + outflow_between(runway_target - timedelta(days=1), runway_target)
            target = buffer - drop * MARGIN_FRACTION
            for point in proj.series:
                if point["date"] == iso(runway_target):
                    return target - point["balance"]
            return target - (proj.series[-1]["balance"] if proj.series else balance)

        burn = _bisect(deficit_for, 0.05, 400.0, 0.0)
    else:
        balance = float(cal["checking_balance"])
        burn = float(cal["daily_discretionary"])

    if balance < 0:
        raise ValueError(
            f"calibration for '{persona_key}' produced a negative starting balance "
            f"({balance:.2f}). Their income likely covers their outflow, so there is no "
            f"shortfall to solve for -- pin checking_balance and daily_discretionary instead."
        )
    if not 1.0 <= burn <= 300.0:
        raise ValueError(
            f"calibration for '{persona_key}' produced an implausible burn rate "
            f"(${burn:.2f}/day). Adjust the targets in personas.json."
        )

    result = project(balance, as_of, horizon_end, burn, future_events, buffer)
    return {
        "checking_balance": money(balance),
        "daily_discretionary": round(burn, 4),
        "runway_target": iso(runway_target),
        "runway_date": iso(result.runway_date) if result.runway_date else None,
        "gap": result.gap,
        "min_balance": result.min_balance,
        "min_balance_date": iso(result.min_balance_date) if result.min_balance_date else None,
    }


def measured_burn(purchases: list[dict], as_of: date, days: int = 30) -> float:
    """The median daily spend an estimator actually sees in the transactions.

    Not quite the knob we solved for: purchase amounts are rounded to cents, so the
    achievable median is quantized. A bank sees purchases, never the parameter that
    generated them, so this is the number to publish.
    """
    window_start = as_of - timedelta(days=days - 1)
    totals: dict[str, float] = {}
    for row in purchases:
        if date.fromisoformat(row["purchase_date"]) >= window_start:
            totals[row["purchase_date"]] = totals.get(row["purchase_date"], 0.0) + row["amount"]
    daily = sorted(
        round(totals.get(iso(window_start + timedelta(days=i)), 0.0), 2) for i in range(days)
    )
    mid = len(daily) // 2
    return round((daily[mid - 1] + daily[mid]) / 2 if len(daily) % 2 == 0 else daily[mid], 2)


# ------------------------------------------------------------------- builders

@dataclass
class Dataset:
    as_of: date
    customers: list[dict] = field(default_factory=list)
    accounts: list[dict] = field(default_factory=list)
    merchants: list[dict] = field(default_factory=list)
    purchases: list[dict] = field(default_factory=list)
    bills: list[dict] = field(default_factory=list)
    deposits: list[dict] = field(default_factory=list)
    withdrawals: list[dict] = field(default_factory=list)
    transfers: list[dict] = field(default_factory=list)
    scenarios: list[dict] = field(default_factory=list)
    calibration: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "as_of": iso(self.as_of),
            "customers": self.customers,
            "accounts": self.accounts,
            "merchants": self.merchants,
            "purchases": self.purchases,
            "bills": self.bills,
            "deposits": self.deposits,
            "withdrawals": self.withdrawals,
            "transfers": self.transfers,
            "scenarios": self.scenarios,
            "calibration": self.calibration,
        }


def load_spec() -> tuple[dict, dict]:
    personas = json.loads((SEED_DIR / "personas.json").read_text())
    merchants = json.loads((SEED_DIR / "merchants.json").read_text())
    return personas, merchants


def stamp(d: date, rng: random.Random, lo_hour: int = 7, hi_hour: int = 22) -> str:
    """Our own intra-day timestamp. Nessie stores day precision only."""
    moment = time(rng.randint(lo_hour, hi_hour), rng.choice([2, 9, 14, 21, 27, 33, 41, 48, 52, 58]))
    return datetime.combine(d, moment).isoformat(timespec="minutes")


def build(as_of: date | None = None, rng_seed: int | None = None) -> Dataset:
    personas_spec, merchants_spec = load_spec()
    as_of = as_of or config.as_of()
    rng = random.Random(rng_seed if rng_seed is not None else config.RANDOM_SEED)
    defaults = personas_spec["defaults"]
    buffer = float(defaults["safety_buffer"])
    history_days = int(defaults["history_days"])

    ds = Dataset(as_of=as_of)

    # ---- merchants ------------------------------------------------------
    by_category: dict[str, list[dict]] = {}
    merchant_by_id: dict[str, dict] = {}
    for m in merchants_spec["merchants"]:
        row = dict(m)
        row.setdefault("is_online", 0)
        row.setdefault("risk_tag", None)
        ds.merchants.append(row)
        merchant_by_id[row["local_id"]] = row
        if row.get("risk_tag") not in RESERVED_TAGS:
            by_category.setdefault(row["category"], []).append(row)

    # ---- counterparties for the scam scenarios ---------------------------
    for cp in personas_spec["counterparties"]:
        ds.customers.append({
            "local_id": cp["local_id"],
            "first_name": cp["first_name"],
            "last_name": cp["last_name"],
            "address": cp["address"],
            "persona_key": None,
            "is_demo_persona": 0,
        })
        ds.accounts.append({
            "local_id": f"acc_{cp['local_id']}",
            "customer_local_id": cp["local_id"],
            "type": "Checking",
            "nickname": cp.get("nickname") or f"{cp['first_name']} account",
            "rewards": 0,
            "balance": 0.0,
        })

    for persona in personas_spec["personas"]:
        _build_persona(ds, persona, merchant_by_id, by_category, as_of,
                       history_days, buffer, defaults, rng)

    _build_scenarios(ds, personas_spec, as_of, rng)
    return ds


def _build_persona(ds, persona, merchant_by_id, by_category, as_of,
                   history_days, buffer, defaults, rng):
    key = persona["key"]
    start = as_of + timedelta(days=int(persona["arrival_offset_days"]))
    history_start = min(start, as_of - timedelta(days=history_days))

    rule = persona["flight_home"]
    flight = end_of_month(as_of, int(rule.get("months_ahead", 1))) if rule.get("rule") == "end_of_month" \
        else as_of + timedelta(days=int(rule.get("offset_days", 60)))

    cal_spec = dict(persona["calibration"])
    rent = float(cal_spec.get("rent_amount", 0.0))

    # ---- accounts -------------------------------------------------------
    acc = persona["accounts"]
    checking_id, savings_id, credit_id = f"acc_{key}_chk", f"acc_{key}_sav", f"acc_{key}_cc"
    ds.customers.append({
        "local_id": f"cust_{key}",
        "first_name": persona["first_name"],
        "last_name": persona["last_name"],
        "address": persona["address"],
        "persona_key": key,
        "language": persona["language"],
        "home_currency": persona["home_currency"],
        "fx_rate": persona["fx_rate"],
        "home_city": persona["home_city"],
        "home_lat": persona["home_lat"],
        "home_lng": persona["home_lng"],
        "arrival_date": iso(start),
        "flight_home_date": iso(flight),
        "is_demo_persona": 1,
    })

    # ---- bill schedule: past occurrences become withdrawals, future ones stay bills
    bill_events: list[tuple[date, float]] = []
    for spec in persona["bills"]:
        amount = float(spec["amount"]) if spec.get("amount") is not None else rent
        trial = spec.get("trial")
        occurrences = monthly_occurrences(int(spec["day"]), history_start, flight)
        trial_end = as_of + timedelta(days=int(trial["free_until_offset_days"])) if trial else None

        for when in occurrences:
            charged = amount
            if trial and trial_end and when < trial_end:
                charged = float(trial.get("amount_before", 0.0))
            if when <= as_of:
                if charged > 0:
                    ds.withdrawals.append({
                        "local_id": f"wd_{spec['local_id']}_{iso(when)}",
                        "account_local_id": checking_id,
                        "type": "withdrawal",
                        "transaction_date": iso(when),
                        "occurred_at": stamp(when, rng, 6, 9),
                        "status": "completed",
                        "medium": "balance",
                        "amount": money(charged),
                        "description": f"{spec['nickname']} - {spec['payee']}",
                        "category": spec["category"],
                    })
            elif charged > 0:
                bill_events.append((when, -charged))

        upcoming = next((w for w in occurrences if w > as_of), None)
        ds.bills.append({
            "local_id": spec["local_id"],
            "account_local_id": checking_id,
            "status": "recurring",
            "payee": spec["payee"],
            "nickname": spec["nickname"],
            "payment_amount": money(amount),
            "payment_date": iso(upcoming) if upcoming else None,
            "recurring_date": int(spec["day"]),
            "creation_date": iso(history_start),
            "upcoming_payment_date": iso(upcoming) if upcoming else None,
            "category": spec["category"],
            "cadence": spec.get("cadence", "monthly"),
            "explanation": spec.get("explanation"),
            "is_trial": 1 if trial else 0,
            "trial_converts_on": iso(trial_end) if trial_end else None,
            "trial_amount_after": money(amount) if trial else None,
        })

    # ---- deposits: recurring ones also count as future income ------------
    deposit_rows: list[dict] = []
    lump_spec = None
    for spec in persona["deposits"]:
        if spec.get("type") == "arrival_lump":
            lump_spec = spec
            continue
        amount = float(spec["amount"])
        cadence = spec.get("cadence")
        if cadence == "monthly":
            dates = monthly_occurrences(int(spec["day"]), history_start, flight)
        elif cadence == "biweekly":
            first = as_of + timedelta(days=int(spec["offset_days"]))
            dates = every_n_days(first, flight, 14)
        else:
            dates = [as_of + timedelta(days=int(spec["offset_days"]))]

        for when in dates:
            if when <= as_of:
                deposit_rows.append({
                    "local_id": f"dep_{spec['local_id']}_{iso(when)}",
                    "account_local_id": checking_id,
                    "type": "deposit",
                    "transaction_date": iso(when),
                    "occurred_at": stamp(when, rng, 8, 11),
                    "status": "completed",
                    "medium": "balance",
                    "amount": money(amount),
                    "description": spec["description"],
                    "category": spec.get("category"),
                    "is_recurring": 1 if cadence else 0,
                })
            elif cadence:
                bill_events.append((when, amount))

    # ---- solve the demo numbers -----------------------------------------
    solved = calibrate(cal_spec, as_of, flight, buffer, bill_events, persona_key=key)
    burn = solved["daily_discretionary"]
    checking_balance = solved["checking_balance"]

    # ---- discretionary purchases on checking -----------------------------
    purchases = _generate_purchases(
        ds, persona, checking_id, by_category, history_start, as_of, burn, rng, medium="balance"
    )

    # ---- credit card purchases, scaled to land on the pinned card balance --
    card_payments = sum(
        w["amount"] for w in ds.withdrawals
        if w["account_local_id"] == checking_id and w["category"] == "credit_card"
    )
    _generate_credit_purchases(
        ds, persona, credit_id, merchant_by_id, by_category,
        history_start, as_of, float(acc["credit"]["balance"]) + card_payments, rng
    )

    # ---- transfers to known payees + one savings move ---------------------
    transfers_out = 0.0
    for payee in persona.get("known_payees", []):
        ds.customers.append({
            "local_id": payee["local_id"],
            "first_name": payee["first_name"],
            "last_name": payee["last_name"],
            "address": payee["address"],
            "persona_key": None,
            "is_demo_persona": 0,
        })
        payee_account = f"acc_{payee['local_id']}"
        ds.accounts.append({
            "local_id": payee_account,
            "customer_local_id": payee["local_id"],
            "type": "Checking",
            "nickname": payee.get("nickname") or payee["first_name"],
            "rewards": 0,
            "balance": 0.0,
        })
        for item in payee.get("history", []):
            when = as_of + timedelta(days=int(item["offset_days"]))
            ds.transfers.append({
                "local_id": f"tr_{payee['local_id']}_{iso(when)}",
                "payer_local_id": checking_id,
                "payee_local_id": payee_account,
                "amount": money(float(item["amount"])),
                "transaction_date": iso(when),
                "occurred_at": stamp(when, rng, 10, 20),
                "status": "completed",
                "medium": "balance",
                "description": item["description"],
                "payee_name": f"{payee['first_name']} {payee['last_name']}",
                "label": "normal",
            })
            transfers_out += float(item["amount"])

    savings_target = float(acc["savings"]["balance"])
    savings_move = 200.0 if persona["role"] == "main" else 0.0
    if savings_move:
        when = as_of - timedelta(days=60)
        ds.transfers.append({
            "local_id": f"tr_{key}_savings_{iso(when)}",
            "payer_local_id": checking_id,
            "payee_local_id": savings_id,
            "amount": money(savings_move),
            "transaction_date": iso(when),
            "occurred_at": stamp(when, rng, 10, 20),
            "status": "completed",
            "medium": "balance",
            "description": "ahorro mensual",
            "payee_name": acc["savings"]["nickname"],
            "label": "normal",
        })
        transfers_out += savings_move

    # ---- the arrival lump absorbs everything so the balance lands exactly --
    spent = sum(p["amount"] for p in purchases)
    withdrawn = sum(w["amount"] for w in ds.withdrawals if w["account_local_id"] == checking_id)
    received = sum(d["amount"] for d in deposit_rows)
    lump = checking_balance + spent + withdrawn + transfers_out - received

    lump_date = as_of + timedelta(days=int(lump_spec["offset_days"])) if lump_spec else start
    lump_date = max(lump_date, history_start)
    if lump >= 0:
        deposit_rows.append({
            "local_id": (lump_spec or {}).get("local_id", f"d_{key}_arrival"),
            "account_local_id": checking_id,
            "type": "deposit",
            "transaction_date": iso(lump_date),
            "occurred_at": stamp(lump_date, rng, 8, 11),
            "status": "completed",
            "medium": "balance",
            "amount": money(lump),
            "description": (lump_spec or {}).get("description", "Initial account funding"),
            "category": (lump_spec or {}).get("category", "family"),
            "is_recurring": 0,
        })
    else:
        # Personas whose income already exceeds their spending would have piled up
        # cash over the history window. A one-off up-front cost (tuition, deposit)
        # absorbs the surplus and is what actually happens to these students.
        ds.withdrawals.append({
            "local_id": f"wd_{key}_upfront",
            "account_local_id": checking_id,
            "type": "withdrawal",
            "transaction_date": iso(lump_date),
            "occurred_at": stamp(lump_date, rng, 8, 11),
            "status": "completed",
            "medium": "balance",
            "amount": money(-lump),
            "description": persona.get("upfront_cost_description", "Tuition and fees"),
            "category": "tuition",
        })
    deposit_rows.append({
        "local_id": f"d_{key}_savings_open",
        "account_local_id": savings_id,
        "type": "deposit",
        "transaction_date": iso(max(start, history_start)),
        "occurred_at": stamp(max(start, history_start), rng, 8, 11),
        "status": "completed",
        "medium": "balance",
        "amount": money(savings_target - savings_move),
        "description": "Savings opening balance",
        "category": "savings",
        "is_recurring": 0,
    })
    ds.deposits.extend(deposit_rows)

    ds.accounts.extend([
        {"local_id": checking_id, "customer_local_id": f"cust_{key}", "type": "Checking",
         "nickname": acc["checking"]["nickname"], "rewards": 0, "balance": money(checking_balance)},
        {"local_id": savings_id, "customer_local_id": f"cust_{key}", "type": "Savings",
         "nickname": acc["savings"]["nickname"], "rewards": 0, "balance": money(savings_target)},
        {"local_id": credit_id, "customer_local_id": f"cust_{key}", "type": "Credit Card",
         "nickname": acc["credit"]["nickname"], "rewards": 0,
         "balance": money(float(acc["credit"]["balance"])),
         "credit_limit": acc["credit"]["credit_limit"], "apr": acc["credit"]["apr"],
         "statement_day": acc["credit"]["statement_day"]},
    ])

    # Re-publish the forecast using the rate the transactions actually show. The
    # knob the solver found and the median the data yields differ by a few cents
    # (cent-rounded amounts quantize the achievable median), and P2's engine can
    # only see the latter. Publishing the measured rate makes our reference
    # projection and their engine agree by construction instead of by luck.
    measured = measured_burn(purchases, as_of)
    if measured > 0:
        reprojected = project(checking_balance, as_of,
                             max(flight, date.fromisoformat(solved["runway_target"])),
                             measured, bill_events, buffer)
        solved["daily_discretionary_solved"] = burn
        solved["daily_discretionary"] = measured
        solved["runway_date"] = iso(reprojected.runway_date) if reprojected.runway_date else None
        solved["gap"] = reprojected.gap
        solved["min_balance"] = reprojected.min_balance
        solved["min_balance_date"] = (iso(reprojected.min_balance_date)
                                      if reprojected.min_balance_date else None)

    solved.update({
        "persona": key,
        "flight_home": iso(flight),
        "arrival": iso(start),
        "rent_amount": money(rent),
        "safety_buffer": buffer,
        "savings_balance": money(savings_target),
        "credit_balance": money(float(acc["credit"]["balance"])),
        "credit_limit": acc["credit"]["credit_limit"],
        "credit_utilization": round(float(acc["credit"]["balance"]) / float(acc["credit"]["credit_limit"]), 4),
        "arrival_lump": money(lump),
        "future_events": [{"date": iso(w), "amount": money(a)} for w, a in sorted(bill_events)],
    })
    ds.calibration[key] = solved


def _break_median_tie(rows: list[dict], as_of: date, days: int = 30) -> bool:
    """Nudge one purchase by a cent so the measured median is not a half-cent tie.

    With an even window the median is the mean of the two middle days, so if their
    cent totals sum to an odd number the median lands on a half cent -- and then
    whether it reads as 31.50 or 31.51 comes down to each side's rounding
    convention. P2's engine and this generator disagreed by a cent on Raj for
    exactly that reason. Removing the tie makes every convention agree.
    """
    window_start = as_of - timedelta(days=days - 1)
    totals: dict[str, float] = {}
    for row in rows:
        if date.fromisoformat(row["purchase_date"]) >= window_start:
            totals[row["purchase_date"]] = totals.get(row["purchase_date"], 0.0) + row["amount"]

    by_day = {(window_start + timedelta(days=i)).isoformat(): 0.0 for i in range(days)}
    by_day.update({d: round(v, 2) for d, v in totals.items()})
    ordered = sorted(by_day.items(), key=lambda kv: kv[1])
    lower, upper = ordered[days // 2 - 1], ordered[days // 2]

    if (round(lower[1] * 100) + round(upper[1] * 100)) % 2 == 0:
        return False   # already exact to the cent

    # Move a cent on the upper middle day. Pick its largest purchase so a cent is
    # never a meaningful share of the amount.
    candidates = [r for r in rows if r["purchase_date"] == upper[0]]
    if not candidates:
        candidates = [r for r in rows if r["purchase_date"] == lower[0]]
    if not candidates:
        return False
    target = max(candidates, key=lambda r: r["amount"])
    target["amount"] = money(target["amount"] + 0.01)
    return True


def _generate_purchases(ds, persona, account_id, by_category, start, as_of,
                        target_burn, rng, medium="balance") -> list[dict]:
    """Daily spending shaped so the *median* of the last 30 daily totals equals
    the calibrated burn rate -- median, because that is what the engine spec uses."""
    spending = persona["spending"]
    weights = spending["category_weights"]
    ranges = spending["typical_amounts"]
    categories = list(weights)
    probabilities = [weights[c] for c in categories]

    rows: list[dict] = []
    day = start
    while day <= as_of:
        weekend = day.weekday() >= 5
        scale = spending["weekend_uplift"] if weekend else 1.0
        # 1-3 purchases most days, occasionally none.
        count = rng.choices([0, 1, 2, 3], weights=[0.08, 0.44, 0.34, 0.14])[0]
        for _ in range(count):
            category = rng.choices(categories, probabilities)[0]
            pool = by_category.get(category) or by_category.get("groceries")
            if not pool:
                continue
            merchant = rng.choice(pool)
            lo, hi = ranges[category]
            amount = rng.uniform(lo, hi) * scale
            rows.append({
                "local_id": f"pur_{account_id}_{iso(day)}_{len(rows)}",
                "account_local_id": account_id,
                "merchant_local_id": merchant["local_id"],
                "amount": amount,
                "purchase_date": iso(day),
                "occurred_at": stamp(day, rng, 7, 22),
                "status": "completed",
                "medium": medium,
                "description": merchant["name"],
                "category": category,
                "is_recurring": 0,
                "label": "normal",
            })
        day += timedelta(days=1)

    # Scale so the recent median daily total matches what we calibrated against.
    window_start = as_of - timedelta(days=29)
    totals: dict[str, float] = {}
    for row in rows:
        if date.fromisoformat(row["purchase_date"]) >= window_start:
            totals[row["purchase_date"]] = totals.get(row["purchase_date"], 0.0) + row["amount"]
    daily = sorted(totals.get(iso(window_start + timedelta(days=i)), 0.0) for i in range(30))
    median = (daily[14] + daily[15]) / 2 if daily else 0.0
    factor = (target_burn / median) if median > 0 else 1.0
    for row in rows:
        row["amount"] = money(max(0.75, row["amount"] * factor))

    _break_median_tie(rows, as_of)

    ds.purchases.extend(rows)
    return rows


def _generate_credit_purchases(ds, persona, account_id, merchant_by_id, by_category,
                               start, as_of, target_total, rng) -> list[dict]:
    """Card spending scaled so the card lands on its pinned balance (utilization
    matters: Ana's card has to sit high enough to trigger the credit tip)."""
    spec = persona["spending"]["credit_card"]
    categories = [c for c in spec["categories"] if by_category.get(c)]
    if not categories or target_total <= 0:
        return []

    rows: list[dict] = []
    day = start
    while day <= as_of:
        if rng.random() < 0.25:
            category = rng.choice(categories)
            merchant = rng.choice(by_category[category])
            rows.append({
                "local_id": f"pur_{account_id}_{iso(day)}_{len(rows)}",
                "account_local_id": account_id,
                "merchant_local_id": merchant["local_id"],
                "amount": rng.uniform(6, 48),
                "purchase_date": iso(day),
                "occurred_at": stamp(day, rng, 9, 23),
                "status": "completed",
                "medium": "credit",
                "description": merchant["name"],
                "category": category,
                "is_recurring": 0,
                "label": "normal",
            })
        day += timedelta(days=1)

    raw = sum(r["amount"] for r in rows)
    factor = target_total / raw if raw > 0 else 1.0
    for row in rows:
        row["amount"] = money(max(1.0, row["amount"] * factor))

    # Rounding leaves a few cents; push them onto the largest purchase so the
    # card balance reconciles exactly against its transaction history.
    residual = money(target_total - sum(r["amount"] for r in rows))
    if rows and abs(residual) >= 0.01:
        biggest = max(rows, key=lambda r: r["amount"])
        biggest["amount"] = money(biggest["amount"] + residual)

    ds.purchases.extend(rows)
    return rows


def _build_scenarios(ds, personas_spec, as_of, rng):
    """Scam and anomaly scenarios stay OUT of history on purpose.

    "You have never paid this payee" and "you have never used this merchant" are
    only true because these never happened in the baseline data.
    """
    accounts_by_persona = {p["key"]: f"acc_{p['key']}_chk" for p in personas_spec["personas"]}
    credit_by_persona = {p["key"]: f"acc_{p['key']}_cc" for p in personas_spec["personas"]}

    for spec in personas_spec["scenarios"]:
        persona = spec["persona"]
        row = {
            "key": spec["key"],
            "persona": persona,
            "kind": spec["kind"],
            "title": spec["title"],
            "expect": spec["expect"],
            "why": spec["why"],
        }
        if spec["kind"] == "transfer":
            row.update({
                "payer_local_id": accounts_by_persona[persona],
                "payee_local_id": f"acc_{spec['payee']}",
                "amount": money(float(spec["amount"])),
                "description": spec["description"],
                "transaction_date": iso(as_of),
                "occurred_at": stamp(as_of, rng, 9, 20),
                "label": "scam" if spec["expect"] == "pause" else "normal",
            })
        else:
            account = credit_by_persona[persona] if spec.get("account") == "credit" \
                else accounts_by_persona[persona]
            base = datetime.combine(as_of, time(14, 5))
            row["purchases"] = [
                {
                    "account_local_id": account,
                    "merchant_local_id": item["merchant"],
                    "amount": money(float(item["amount"])),
                    "purchase_date": iso(as_of),
                    "occurred_at": (base + timedelta(minutes=item["minutes_from_start"]))
                                   .isoformat(timespec="minutes"),
                    "status": "completed",
                    "medium": "credit" if spec.get("account") == "credit" else "balance",
                    "label": "fraud",
                    "scenario": spec["key"],
                }
                for item in spec["purchases"]
            ]
        ds.scenarios.append(row)


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


if __name__ == "__main__":
    data = build()
    print(json.dumps(data.calibration, indent=2))
