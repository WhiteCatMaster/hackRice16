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
| Frontend | P4 | **done** — see [frontend/README.md](frontend/README.md) |
| Frontend ↔ backend | all | **integrated** — see below, and `tests/test_integration.py` |
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

Then run the web app (Node 20+, `npm i -g pnpm`):

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

150 tests across the four layers, including a full push-and-sync round trip
against an in-memory Nessie and the whole §9 demo path over real HTTP.

`tests/test_integration.py` is the seam: it reads the required fields out of
`frontend/lib/contract.ts` and asserts the API answers with every one of them,
that `mocks/` satisfies the same contract, and that every endpoint the frontend
calls exists on both sides. Drift between the layers fails there rather than on
stage.

## The API

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.api.app:app --port 8000
curl -s localhost:8000/api/health | python -m json.tool
```

No FastAPI, or a failed install? `python -m backend.api.serve 8000` serves the
identical routes from the standard library. Point the frontend at it with
`LANDED_API_BASE=http://127.0.0.1:8000` in `frontend/.env.local`.

## The whole thing, end to end

Three terminals, and the demo is live on `http://localhost:3000`:

```bash
python -m seed.reset_demo --arm                      # 1. data, with the scenarios fired
.venv/bin/uvicorn backend.api.app:app --port 8000    # 2. the API over P2's engine
cd frontend && pnpm dev                              # 3. the web app
```

`frontend/.env.local` is what puts the app in live mode:

```
LANDED_API_BASE=http://127.0.0.1:8000
```

Without it the app reads `mocks/` and says so in the top bar. Check which mode
you are in before demoing:

```bash
curl -s localhost:8000/api/health | python -m json.tool   # engine.from_p2 lists who answers
curl -s localhost:3000/api/users/ana/summary              # the same numbers, through the app
```

**`--arm` matters.** A freshly reset cache has no scam or anomaly scenarios
fired, so the Safety centre is empty — while `mocks/` ships with all four alerts,
because the fixtures are exported with every scenario fired. Mock mode looked
full and live mode looked broken. `--arm` fires them, so both show the same
screen; `tests/test_integration.py` holds that to be true.

## Before the demo

```bash
python -m seed.reset_demo --arm     # back to a known state, scenarios armed
python -m backend.engine.export     # engine fixtures + the diff against P1's numbers
```

Approving an action in the copilot really does move money in the cache, so reset
between rehearsals.
