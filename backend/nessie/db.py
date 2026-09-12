"""Local SQLite cache.

Two kinds of column live side by side here:

  * mirrored  - a faithful copy of what Nessie returned (so the demo never depends
                on Nessie being up);
  * local     - things Nessie has no concept of: credit limits, card freezes,
                intra-day timestamps, scam labels, home currency.

Anything local is prefixed in the docs and flagged in `local_only` so the pitch can
honestly say which numbers are ours rather than the bank's.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from . import config

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS customers (
    id              TEXT PRIMARY KEY,
    local_id        TEXT UNIQUE,
    first_name      TEXT,
    last_name       TEXT,
    address         TEXT,
    -- local only --
    persona_key     TEXT,
    language        TEXT,
    home_currency   TEXT,
    fx_rate         REAL,
    home_city       TEXT,
    home_lat        REAL,
    home_lng        REAL,
    arrival_date    TEXT,
    flight_home_date TEXT,
    is_demo_persona INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS accounts (
    id              TEXT PRIMARY KEY,
    local_id        TEXT UNIQUE,
    customer_id     TEXT,
    type            TEXT,
    nickname        TEXT,
    rewards         REAL,
    balance         REAL,
    -- local only --
    credit_limit    REAL,
    apr             REAL,
    statement_day   INTEGER,
    is_frozen       INTEGER DEFAULT 0,
    frozen_reason   TEXT
);

CREATE TABLE IF NOT EXISTS merchants (
    id              TEXT PRIMARY KEY,
    local_id        TEXT UNIQUE,
    name            TEXT,
    category        TEXT,
    address         TEXT,
    lat             REAL,
    lng             REAL,
    -- local only --
    is_online       INTEGER DEFAULT 0,
    risk_tag        TEXT
);

CREATE TABLE IF NOT EXISTS purchases (
    id              TEXT PRIMARY KEY,
    local_id        TEXT UNIQUE,
    account_id      TEXT,
    merchant_id     TEXT,
    amount          REAL,
    purchase_date   TEXT,
    status          TEXT,
    medium          TEXT,
    description     TEXT,
    -- local only --
    occurred_at     TEXT,      -- full timestamp; Nessie stores day precision only
    category        TEXT,
    is_recurring    INTEGER DEFAULT 0,
    label           TEXT,      -- 'normal' | 'fraud'
    scenario        TEXT
);

CREATE TABLE IF NOT EXISTS bills (
    id              TEXT PRIMARY KEY,
    local_id        TEXT UNIQUE,
    account_id      TEXT,
    status          TEXT,
    payee           TEXT,
    nickname        TEXT,
    payment_amount  REAL,
    payment_date    TEXT,
    recurring_date  INTEGER,
    creation_date   TEXT,
    upcoming_payment_date TEXT,
    -- local only --
    category        TEXT,
    cadence         TEXT,
    explanation     TEXT,
    is_trial        INTEGER DEFAULT 0,
    trial_converts_on TEXT,
    trial_amount_after REAL
);

CREATE TABLE IF NOT EXISTS deposits (
    id              TEXT PRIMARY KEY,
    local_id        TEXT UNIQUE,
    account_id      TEXT,
    type            TEXT,
    transaction_date TEXT,
    status          TEXT,
    medium          TEXT,
    amount          REAL,
    description     TEXT,
    -- local only --
    occurred_at     TEXT,
    category        TEXT,
    is_recurring    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS withdrawals (
    id              TEXT PRIMARY KEY,
    local_id        TEXT UNIQUE,
    account_id      TEXT,
    type            TEXT,
    transaction_date TEXT,
    status          TEXT,
    medium          TEXT,
    amount          REAL,
    description     TEXT,
    -- local only --
    occurred_at     TEXT,
    category        TEXT
);

CREATE TABLE IF NOT EXISTS transfers (
    id              TEXT PRIMARY KEY,
    local_id        TEXT UNIQUE,
    payer_id        TEXT,
    payee_id        TEXT,
    amount          REAL,
    transaction_date TEXT,
    status          TEXT,
    medium          TEXT,
    description     TEXT,
    -- local only --
    occurred_at     TEXT,
    payee_name      TEXT,
    label           TEXT,      -- 'normal' | 'scam'
    scenario        TEXT
);

-- Local-only: maps a persona's known counterparties so the risk engine can ask
-- "has this user ever paid this payee before?" without a second Nessie round trip.
CREATE TABLE IF NOT EXISTS payees (
    account_id      TEXT,
    payee_account_id TEXT,
    payee_name      TEXT,
    first_paid_on   TEXT,
    times_paid      INTEGER DEFAULT 0,
    total_paid      REAL DEFAULT 0,
    PRIMARY KEY (account_id, payee_account_id)
);

-- local_id -> nessie id, written by seed.py so sync.py can re-attach local fields
CREATE TABLE IF NOT EXISTS id_map (
    entity          TEXT,
    local_id        TEXT,
    nessie_id       TEXT,
    PRIMARY KEY (entity, local_id)
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT,
    finished_at     TEXT,
    source          TEXT,      -- 'nessie' | 'local'
    rows            INTEGER,
    api_calls       INTEGER,
    note            TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key             TEXT PRIMARY KEY,
    value           TEXT
);

CREATE INDEX IF NOT EXISTS ix_purchases_account ON purchases(account_id, purchase_date);
CREATE INDEX IF NOT EXISTS ix_bills_account     ON bills(account_id);
CREATE INDEX IF NOT EXISTS ix_deposits_account  ON deposits(account_id, transaction_date);
CREATE INDEX IF NOT EXISTS ix_transfers_payer   ON transfers(payer_id, transaction_date);
CREATE INDEX IF NOT EXISTS ix_accounts_customer ON accounts(customer_id);
"""

TABLES = [
    "customers", "accounts", "merchants", "purchases", "bills",
    "deposits", "withdrawals", "transfers", "payees", "id_map",
]


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    db_path = Path(path or config.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def wipe(conn: sqlite3.Connection) -> None:
    """Empty the cache but keep the schema."""
    for table in TABLES:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()


def columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]


def upsert(conn: sqlite3.Connection, table: str, rows: Iterable[dict]) -> int:
    """Insert-or-replace, ignoring keys that aren't columns and JSON-encoding dicts."""
    rows = list(rows)
    if not rows:
        return 0
    allowed = set(columns(conn, table))
    count = 0
    for row in rows:
        clean = {}
        for key, value in row.items():
            if key not in allowed:
                continue
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            elif isinstance(value, bool):
                value = int(value)
            clean[key] = value
        if not clean:
            continue
        cols = ",".join(clean)
        marks = ",".join("?" * len(clean))
        conn.execute(
            f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({marks})",
            list(clean.values()),
        )
        count += 1
    conn.commit()
    return count


def set_meta(conn: sqlite3.Connection, key: str, value: Any) -> None:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, default=str)
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", (key, value))
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return row["value"]


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
        for t in TABLES if t != "id_map"
    }


def rebuild_payees(conn: sqlite3.Connection) -> int:
    """Derive the known-payee table from transfer history (risk engine input)."""
    conn.execute("DELETE FROM payees")
    conn.execute(
        """
        INSERT INTO payees (account_id, payee_account_id, payee_name,
                            first_paid_on, times_paid, total_paid)
        SELECT payer_id, payee_id, MIN(COALESCE(payee_name,'')),
               MIN(transaction_date), COUNT(*), SUM(amount)
        FROM transfers
        WHERE status IN ('completed','executed','pending') AND COALESCE(label,'normal') <> 'scam'
        GROUP BY payer_id, payee_id
        """
    )
    conn.commit()
    return conn.execute("SELECT COUNT(*) c FROM payees").fetchone()["c"]
