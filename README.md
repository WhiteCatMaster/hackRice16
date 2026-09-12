# EXTreasurer

A financial copilot for international students in their first year in the US, with
built-in scam protection. Built on Capital One's Nessie mock banking API.

Full plan: [begin.md](begin.md). Team split, timeline, demo script and pitch live there.

## Status

| Layer | Owner | State |
|---|---|---|
| Data & Nessie integration | P1 | **done** — see [docs/data-layer.md](docs/data-layer.md) |
| Engine (forecast & risk) | P2 | **running, source still missing** — restored from bytecode, see [below](#the-engine-is-not-in-the-repo) |
| Backend API & agent | P3 | **done** — see [docs/api.md](docs/api.md) |
| Frontend (web) | P4 | **done** — see [frontend/README.md](frontend/README.md) |
| Frontend (mobile) | P4 | **done** — see [mobile/README.md](mobile/README.md) |
| Frontend ↔ backend | all | **integrated** — see below, and `tests/test_integration.py` |
| Pitch, deck, demo video | P4 | not started |

## The engine is not in the repo

`backend/engine/` has no `.py` source. It was never committed on any branch, so
git has nothing to restore and neither does the stash. What survived was the
compiled output in `__pycache__`, last built on 2026-09-11.

**The engine runs again anyway.** Python imports a `.pyc` sitting where its source
belongs, so the ten modules are restored that way (`backend/engine/projection.pyc`
and friends). All twelve capabilities resolve to `backend.engine`, the five
`tests/test_integration.py` failures went green together — they were that one
absence, not five bugs — and both CLIs below work.

Three things this does not fix:

- **Nobody can edit the engine.** Bytecode is not source. Whoever still has those
  files should commit them; until then the engine is frozen.
- **It is built for one Python version** (3.13, what `.venv` runs). On any other
  the import fails and `backend/api/engine_port.py` falls back to P3's
  `backend/api/reference.py` — per function, re-checked every call — with a
  warning in the log. Nothing crashes, which is what makes it easy to miss.
- **`.pyc` is gitignored**, so these files are tracked only because they were
  force-added. Treat the copy in git as a hedge, not a substitute.

Check which side is answering before you demo:

```bash
curl -s localhost:8000/api/health | python -m json.tool   # engine_module, and a per-capability map
```

Any payload says so itself — `"_engine": "backend.engine"`, or `"p3-reference"`
if it fell back. What the reference does not carry: `already_short` and
`max_safe_through` on affordability, and `days_gained` on a fix's effect.

```bash
python -m backend.engine           # the forecast, the fixes and the scam checks for Ana
python -m backend.engine.export    # engine fixtures + the diff against P1's numbers
```

`export` rewrites six fixtures in `mocks/`, so run it only when you mean to. It
currently reports `OUT OF TOLERANCE`: the engine puts Ana's gap at $425.90 where
P1's published calibration says $409.91, a difference of exactly one $15.99
streaming bill and one future event. It is not date drift — it survives
`DEMO_AS_OF=2026-09-11` — and it predates the restore. Worth settling before the
demo, since mock mode and live mode answer that question differently.

## Quick start

No dependencies for the data layer — Python 3.11+, standard library only.

```bash
cp .env.example .env          # add NESSIE_API_KEY when you have one
python -m seed.reset_demo     # generate, validate, cache, and write mocks/
python -m backend.nessie.repo # see what is in the cache
```

`python -m backend.engine` runs, but from restored bytecode rather than source.
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

The copilot is one of the six tabs there, not a modal behind an icon — it is the
screen people come back to.

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

## Bring your own model

Neither app needs a key in this repository to talk to a model. The copilot — on
a phone or on a laptop — takes the user's own:

- **Web**: Copilot → *Use your own key*. Kept in that browser's `localStorage`.
- **Phone**: Ask → the key button, or `/model-key`. Kept in the phone's keystore.

Gemini, Claude, or anything speaking OpenAI's chat-completions shape (OpenAI,
OpenRouter, Groq, a model on your own laptop). It rides along with the question
as `X-Model-*` headers, is spent on that one turn, and is never written to the
server's disk or logs — [docs/api.md](docs/api.md#using-your-own-key) has the
headers, the failure modes and why it is headers rather than a body.

The server's own `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` still
work as the fallback, and with none of them the scripted router answers every §9
question with real numbers.

## Tests

```bash
python -m seed.reset_demo --arm     # the state the suite expects
python -m unittest discover tests
```

141 tests across the four layers, including a full push-and-sync round trip
against an in-memory Nessie, a whole chat turn against a stub model, and the
§9 demo path over real HTTP.

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

The second line rewrites six fixtures in `mocks/`; run it only when you mean to.

Approving an action in the copilot really does move money in the cache, so reset
between rehearsals.
