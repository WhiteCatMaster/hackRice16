"""Shared configuration for the data layer.

Reads .env by hand so the whole P1 layer stays dependency-free.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        # Real environment always wins over the file.
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ROOT / ".env")

NESSIE_BASE_URL = os.environ.get("NESSIE_BASE_URL", "http://api.nessieisreal.com").rstrip("/")
NESSIE_API_KEY = os.environ.get("NESSIE_API_KEY", "").strip()

DB_PATH = Path(os.environ.get("LANDED_DB") or (ROOT / "data" / "landed.db"))
if not DB_PATH.is_absolute():
    DB_PATH = ROOT / DB_PATH

MOCKS_DIR = ROOT / "mocks"
SEED_DIR = ROOT / "seed"

RANDOM_SEED = int(os.environ.get("DEMO_RANDOM_SEED") or 20260911)


def as_of() -> date:
    """The date the demo pretends 'today' is. Everything is generated relative to it."""
    raw = (os.environ.get("DEMO_AS_OF") or "").strip()
    if raw:
        return date.fromisoformat(raw)
    return date.today()


def has_api_key() -> bool:
    return bool(NESSIE_API_KEY) and NESSIE_API_KEY != "put_your_key_here"
