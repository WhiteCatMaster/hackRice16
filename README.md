# Landed

A financial copilot for international students in their first year in the US, with
built-in scam protection. Built on Capital One's Nessie mock banking API.

Full plan: [begin.md](begin.md). Team split, timeline, demo script and pitch live there.

## Status

| Layer | Owner | State |
|---|---|---|
| Data & Nessie integration | P1 | **done** — see [docs/data-layer.md](docs/data-layer.md) |
| Engine (forecast & risk) | P2 | **done** — see [docs/engine.md](docs/engine.md) |
| Backend API & agent | P3 | **done** — see [docs/api.md](docs/api.md) |
| Frontend | P4 | **screens done** — see [frontend/README.md](frontend/README.md) |
| Pitch, deck, demo video | P4 | not started |

## Quick start

No dependencies for the data layer — Python 3.11+, standard library only.

```bash
cp .env.example .env          # add NESSIE_API_KEY when you have one
python -m seed.reset_demo     # generate, validate, cache, and write mocks/
python -m backend.nessie.repo # see what is in the cache
python -m backend.engine      # the forecast, the fixes and the scam checks for Ana
```

That works with no API key and no network. With a key:

```bash
python -m seed.seed --push    # push the dataset to Nessie, then cache it
```

Then run the web app:

```bash
cd frontend && pnpm install && pnpm dev    # http://localhost:3000
```

It reads `mocks/` directly, so it works with no backend. Point
`LANDED_API_BASE` at P3's FastAPI and every screen switches to live data.

Then:

- **P3** — `from backend.engine import summary, forecast, check_transfer, alerts`;
  one call per endpoint, already in the contract's shape. See [docs/engine.md](docs/engine.md).
- **P4** — `mocks/api_*.json` fix every response shape in the contract, and
  `frontend/lib/contract.ts` types them.
- **P4** — the screens are in `frontend/`.

## Tests

```bash
python -m unittest discover tests
```

119 tests across the three layers, including a full push-and-sync round trip
against an in-memory Nessie and the whole §9 demo path over real HTTP.

## The API

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.api.app:app --port 8000
curl -s localhost:8000/api/health | python -m json.tool
```

No FastAPI, or a failed install? `python -m backend.api.serve 8000` serves the
identical routes from the standard library. Point the frontend at it with
`LANDED_API_BASE=http://127.0.0.1:8000` in `frontend/.env.local`.

## Before the demo

```bash
python -m seed.reset_demo && python -m seed.scenarios --clear
python -m backend.engine.export     # engine fixtures + the diff against P1's numbers
```
