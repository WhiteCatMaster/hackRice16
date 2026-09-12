"""Read helpers over the local cache.

This is the seam between P1 and the rest of the team: P2's engine and P3's API
call these instead of writing SQL or touching Nessie. Everything returns plain
dicts and lists, so it is trivially mockable.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from . import db


def _rows(conn, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params)]


def _row(conn, sql: str, params: tuple = ()) -> dict | None:
    found = conn.execute(sql, params).fetchone()
    return dict(found) if found else None


def as_of(conn) -> date:
    value = db.get_meta(conn, "as_of")
    return date.fromisoformat(value) if value else date.today()


def personas(conn) -> list[dict]:
    return _rows(conn, "SELECT * FROM customers WHERE is_demo_persona=1 ORDER BY persona_key")


def customer(conn, persona_key: str) -> dict | None:
    return _row(conn, "SELECT * FROM customers WHERE persona_key=?", (persona_key,))


def resolve_customer(conn, ref: str) -> dict | None:
    """Accept either a persona key ('ana') or a raw customer id."""
    return customer(conn, ref) or _row(conn, "SELECT * FROM customers WHERE id=?", (ref,))


def accounts(conn, customer_id: str) -> list[dict]:
    return _rows(conn, "SELECT * FROM accounts WHERE customer_id=? ORDER BY type", (customer_id,))


def account(conn, account_id: str) -> dict | None:
    return _row(conn, "SELECT * FROM accounts WHERE id=?", (account_id,))


def account_of_type(conn, customer_id: str, kind: str) -> dict | None:
    return _row(conn, "SELECT * FROM accounts WHERE customer_id=? AND type=?", (customer_id, kind))


def purchases(conn, account_id: str, since: date | None = None, limit: int | None = None) -> list[dict]:
    sql = ("SELECT p.*, m.name AS merchant_name, m.category AS merchant_category, "
           "m.lat, m.lng, m.is_online "
           "FROM purchases p LEFT JOIN merchants m ON m.id = p.merchant_id "
           "WHERE p.account_id=?")
    params: list[Any] = [account_id]
    if since:
        sql += " AND p.purchase_date >= ?"
        params.append(since.isoformat())
    sql += " ORDER BY COALESCE(p.occurred_at, p.purchase_date) DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return _rows(conn, sql, tuple(params))


def bills(conn, account_id: str) -> list[dict]:
    return _rows(
        conn,
        "SELECT * FROM bills WHERE account_id=? ORDER BY COALESCE(upcoming_payment_date, payment_date)",
        (account_id,),
    )


def deposits(conn, account_id: str) -> list[dict]:
    return _rows(conn, "SELECT * FROM deposits WHERE account_id=? ORDER BY transaction_date", (account_id,))


def withdrawals(conn, account_id: str) -> list[dict]:
    return _rows(conn, "SELECT * FROM withdrawals WHERE account_id=? ORDER BY transaction_date", (account_id,))


def transfers(conn, account_id: str) -> list[dict]:
    return _rows(
        conn,
        "SELECT * FROM transfers WHERE payer_id=? OR payee_id=? ORDER BY transaction_date DESC",
        (account_id, account_id),
    )


def known_payee(conn, account_id: str, payee_account_id: str) -> dict | None:
    """The 'have I ever paid this person before?' lookup the risk engine needs."""
    return _row(
        conn,
        "SELECT * FROM payees WHERE account_id=? AND payee_account_id=?",
        (account_id, payee_account_id),
    )


def known_merchant(conn, account_id: str, merchant_id: str) -> dict | None:
    return _row(
        conn,
        "SELECT merchant_id, COUNT(*) AS times_used, MIN(purchase_date) AS first_used, "
        "AVG(amount) AS avg_amount FROM purchases "
        "WHERE account_id=? AND merchant_id=? GROUP BY merchant_id",
        (account_id, merchant_id),
    )


def daily_spend(conn, account_id: str, days: int = 30) -> dict[str, float]:
    """Date -> total purchases, zero-filled. The engine's burn-rate input."""
    end = as_of(conn)
    start = end - timedelta(days=days - 1)
    totals = {(start + timedelta(days=i)).isoformat(): 0.0 for i in range(days)}
    for row in conn.execute(
        "SELECT purchase_date, SUM(amount) total FROM purchases "
        "WHERE account_id=? AND purchase_date BETWEEN ? AND ? GROUP BY purchase_date",
        (account_id, start.isoformat(), end.isoformat()),
    ):
        totals[row["purchase_date"]] = round(row["total"], 2)
    return totals


def category_spend(conn, account_id: str, days: int = 30) -> dict[str, float]:
    end = as_of(conn)
    start = end - timedelta(days=days - 1)
    return {
        r["category"] or "other": round(r["total"], 2)
        for r in conn.execute(
            "SELECT category, SUM(amount) total FROM purchases "
            "WHERE account_id=? AND purchase_date BETWEEN ? AND ? "
            "GROUP BY category ORDER BY total DESC",
            (account_id, start.isoformat(), end.isoformat()),
        )
    }


def snapshot(conn, persona_key: str) -> dict:
    """Everything about one persona in a single call.

    P2 can feed this straight into the forecast; P3 can hand most of it to the
    agent as tool output.
    """
    person = resolve_customer(conn, persona_key)
    if not person:
        return {}
    accs = accounts(conn, person["id"])
    checking = next((a for a in accs if a["type"] == "Checking"), None)
    credit = next((a for a in accs if a["type"] == "Credit Card"), None)

    out = {
        "customer": person,
        "accounts": accs,
        "as_of": as_of(conn).isoformat(),
        "flight_home_date": person.get("flight_home_date"),
        "home_currency": person.get("home_currency"),
        "fx_rate": person.get("fx_rate"),
        "language": person.get("language"),
    }
    if checking:
        out.update({
            "checking_account_id": checking["id"],
            "bills": bills(conn, checking["id"]),
            "deposits": deposits(conn, checking["id"]),
            "withdrawals": withdrawals(conn, checking["id"]),
            "transfers": transfers(conn, checking["id"]),
            "purchases": purchases(conn, checking["id"]),
            "daily_spend_30d": daily_spend(conn, checking["id"]),
            "category_spend_30d": category_spend(conn, checking["id"]),
        })
    if credit:
        limit = credit.get("credit_limit") or 0
        out["credit"] = {
            "account_id": credit["id"],
            "balance": credit["balance"],
            "limit": limit,
            "utilization": round(credit["balance"] / limit, 4) if limit else None,
            "apr": credit.get("apr"),
            "statement_day": credit.get("statement_day"),
            "purchases": purchases(conn, credit["id"]),
            "_simulated": ["limit", "apr", "utilization"],
        }
    return out


def expected_forecast(conn, persona_key: str) -> dict | None:
    """What P1's calibration says the forecast should produce.

    P2 can assert against this in their unit tests; if their engine disagrees with
    these numbers, one of us has a bug and we find out before the demo.
    """
    calibration = db.get_meta(conn, "calibration") or {}
    return calibration.get(persona_key)


def scenarios(conn, persona_key: str | None = None) -> list[dict]:
    items = db.get_meta(conn, "scenarios") or []
    if persona_key:
        items = [s for s in items if s.get("persona") == persona_key]
    return items


def summary(conn) -> dict:
    """Human-readable health check of the cache."""
    return {
        "as_of": as_of(conn).isoformat(),
        "counts": db.counts(conn),
        "personas": [p["persona_key"] for p in personas(conn)],
        "last_nessie_sync": db.get_meta(conn, "last_nessie_sync"),
    }


if __name__ == "__main__":
    conn = db.connect()
    db.init(conn)
    print(json.dumps(summary(conn), indent=2))
    snap = snapshot(conn, "ana")
    if snap:
        print(json.dumps({
            "accounts": [(a["type"], a["balance"], a.get("credit_limit")) for a in snap["accounts"]],
            "bills": [(b["nickname"], b["payment_amount"], b["upcoming_payment_date"]) for b in snap["bills"]],
            "category_spend_30d": snap["category_spend_30d"],
            "expected_forecast": expected_forecast(conn, "ana"),
        }, indent=2, default=str)[:1600])
