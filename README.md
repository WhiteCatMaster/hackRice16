# ExchangeTreasurer

A financial copilot for international students in their first year in the US, with
built-in scam protection. Built on Capital One's Nessie mock banking API.

Full plan: [begin.md](begin.md). Team split, timeline, demo script and pitch live there.

## Status

| Layer | Owner | State |
|---|---|---|
| Data & Nessie integration | P1 | **done** — see [docs/data-layer.md](docs/data-layer.md) |
| Engine (forecast & risk) | P2 | **source missing** — see [below](#the-engine-is-not-in-the-repo). The API is running on P3's reference |
| Backend API & agent | P3 | **done** — see [docs/api.md](docs/api.md) |
| Frontend (web) | P4 | **done** — see [frontend/README.md](frontend/README.md) |
| Frontend (mobile) | P4 | **done** — see [mobile/README.md](mobile/README.md) |
| Frontend ↔ backend | all | **integrated** — see below, and `tests/test_integration.py` |
| Pitch, deck, demo video | P4 | not started |

## The engine is not in the repo

`backend/engine/` contains no source — only a `__pycache__` of a version that was
importable on 2026-09-11 at 23:47. The directory was never committed and is not
gitignored, so git has nothing to restore and neither does the stash. Whoever has
those files on their machine should commit them.

Nothing crashes, which is why this is easy to miss. `backend/api/engine_port.py`
resolves each capability to `backend.engine` if it has one and P3's
`backend/api/reference.py` otherwise, per function, re-checked every call. With
the module gone every capability falls to the reference, and the API keeps
answering with P1's calibrated numbers. Check which side is talking:

```bash
curl -s localhost:8000/api/health | python -m json.tool   # every capability reads "p3-reference"
```

Any payload will also say so itself — `"_engine": "p3-reference"`.

What the reference does not carry: `already_short` and `max_safe_through` on
affordability, and `days_gained` on a fix's effect. The deleted
`projection.py` and `forecast.py` were the only source of those three fields, so
the five failures in `tests/test_integration.py` are all that one absence rather
than five separate bugs. Restore the engine and they go green together.

These commands need it too, and currently exit with an import error:

```bash
python -m backend.engine           # the forecast, the fixes and the scam checks for Ana
python -m backend.engine.export    # engine fixtures + the diff against P1's numbers
```

## Quick start

No dependencies for the data layer — Python 3.11+, standard library only.

```bash
cp .env.example .env          # add NESSIE_API_KEY when you have one
python -m seed.reset_demo     # generate, validate, cache, and write mocks/
python -m backend.nessie.repo # see what is in the cache
```

`python -m backend.engine` is in a lot of older notes; it does not currently run.
See [below](#the-engine-is-not-in-the-repo).

That works with no API key and no network. With a key:

```bash
python -m seed.seed --push    # push the dataset to Nessie, then cache it
```

Then run the web app (Node 20+, `npm i -g pnpm`):

```bash
cd frontend && pnpm install && pnpm dev    # http://localhost:3000
```

It reads `mocks/` directly, so it works with no backend. Point
`TREASURER_API_BASE` at P3's FastAPI and every screen switches to live data.

Or run it on a phone (Expo, same Node):

```bash
cd mobile && npm install && npm start    # then i / a / w, or scan with Expo Go
```

Same screens, same contract, same two modes — Metro bundles `mocks/` straight
out of the repository root, so it has real data with no backend either. See
[mobile/README.md](mobile/README.md); the one thing that differs is that a phone
calls the API directly, so live mode needs CORS rather than a proxy.

Then:

- **P3** — `from backend.engine import summary, forecast, check_transfer, alerts`;
  one call per endpoint, already in the contract's shape. That import is the
  intended seam, but it resolves to nothing today — go through
  `backend/api/engine_port.py`, which falls back for you. See [docs/api.md](docs/api.md).
- **P4** — `mocks/api_*.json` fix every response shape in the contract, and
  `frontend/lib/contract.ts` types them.
- **P4** — the screens are in `frontend/` (web) and `mobile/` (React Native).
  `mobile/lib/contract.ts` is a copy of the web one; `cd mobile && npm run check`
  fails if the two ever drift.

## Tests

```bash
python -m seed.reset_demo --arm     # the state the suite expects
python -m unittest discover tests
```

113 tests across the four layers, including a full push-and-sync round trip
against an in-memory Nessie and the whole §9 demo path over real HTTP.

Run `--arm` first. Parts of `test_integration.py` assert that live mode shows the
same alerts the fixtures ship with, and an unarmed cache has none of them — so
those tests fail on a cache that is merely stale, which reads as a code bug and
is not one.

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
`TREASURER_API_BASE=http://127.0.0.1:8000` in `frontend/.env.local`.

## The whole thing, end to end

Three terminals, and the demo is live on `http://localhost:3000`:

```bash
python -m seed.reset_demo --arm                      # 1. data, with the scenarios fired
.venv/bin/uvicorn backend.api.app:app --port 8000    # 2. the API (on P3's reference)
cd frontend && pnpm dev                              # 3. the web app
```

`frontend/.env.local` is what puts the app in live mode:

```
TREASURER_API_BASE=http://127.0.0.1:8000
```

Without it the app reads `mocks/` and says so in the top bar. Check which mode
you are in before demoing:

```bash
curl -s localhost:8000/api/health | python -m json.tool   # names who answered each capability
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

The second line needs the engine source back before it runs; skip it until then.

Approving an action in the copilot really does move money in the cache, so reset
between rehearsals.
