# EXTreasurer

A financial copilot for international students in their first year in the US.
It tells a student whether their money lasts until the flight home, explains US
banking in their own language, and pauses a transfer that looks like a scam
before the money leaves. Built on Capital One's
[Nessie](https://nessieisreal.com) mock banking API.

Production: **https://exchangetreasurer.us**

```
Ana, from Bilbao, studying in Omaha
  runway     money lasts until 2026-10-10, flight home is 2026-10-31
  copilot    "¿Puedo permitirme ir a Chicago este finde?"  → "Ahora mismo no" + a fix to approve
  safety     $800 "URGENT apartment deposit" to a new payee → paused, score 84
```

## What is in this repository

| Path | What it is | Docs |
|---|---|---|
| `backend/nessie/` | Nessie REST client, SQLite cache, sync. Standard library only | [data layer](docs/data-layer.md), [Nessie notes](docs/nessie-api-notes.md) |
| `seed/` | Generates the demo dataset, pushes it to Nessie, fires scam scenarios, resets the demo | [data layer](docs/data-layer.md) |
| `backend/engine/` | Forecast, affordability, fixes, scam and anomaly scoring. **Ships as bytecode only** | [engine](docs/engine.md) |
| `backend/api/` | HTTP API (FastAPI, or the same routes on `http.server`) and the confirmation gate | [API reference](docs/api.md) |
| `backend/agent/` | The copilot: Gemini, Claude or any OpenAI-compatible model with tools, or a scripted router | [agent](docs/agent.md) |
| `mocks/` | JSON fixtures shaped like every API response, so both apps run with no backend | [data layer](docs/data-layer.md#fixtures-in-mocks) |
| `frontend/` | Web app, Next.js 16 | [frontend/README.md](frontend/README.md) |
| `mobile/` | Phone app, Expo SDK 57 / React Native | [mobile/README.md](mobile/README.md) |
| `exchange-treasurer/` | A fresh Expo template, not yet wired to anything | [exchange-treasurer/README.md](exchange-treasurer/README.md) |
| `tests/` | 141 Python tests across data, engine, API, agent and the frontend contract | [testing](docs/testing.md) |
| `begin.md` | The original hackathon plan: problem, design rules, contract, demo script. Code comments cite its sections (§6, §7, §9) | — |

## Quick start

No API keys, no network. Python 3.13 and Node 20+ with pnpm.

```bash
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m seed.reset_demo --arm             # build the demo data, fire the scam scenarios
.venv/bin/uvicorn backend.api.app:app --port 8000     # the API, in another terminal

cd frontend && pnpm install
echo 'TREASURER_API_BASE=http://127.0.0.1:8000' > .env.local
pnpm dev                                              # http://localhost:3000
```

Skip the backend entirely and the web app still runs, reading `mocks/`. The top
bar then reads **RUNNING ON FIXTURES**. Full instructions, including the phone
app: [docs/setup.md](docs/setup.md).

## Documentation

| Read this | For |
|---|---|
| [docs/architecture.md](docs/architecture.md) | How the layers fit, the design rules and where each is enforced |
| [docs/setup.md](docs/setup.md) | Running everything locally, on a phone, over HTTPS |
| [docs/configuration.md](docs/configuration.md) | Every environment variable, in all three `.env` files |
| [docs/data-layer.md](docs/data-layer.md) | The dataset, calibration, cache, scenarios, fixtures |
| [docs/engine.md](docs/engine.md) | Forecast and risk engine, its bytecode-only state, the fallback |
| [docs/api.md](docs/api.md) | Endpoint reference with real payloads |
| [docs/agent.md](docs/agent.md) | Model providers, tools, the scripted router, bring-your-own-key |
| [docs/nessie-api-notes.md](docs/nessie-api-notes.md) | What the live Nessie sandbox actually does, and the workarounds |
| [docs/testing.md](docs/testing.md) | Test suites and the cross-layer checks |
| [docs/demo.md](docs/demo.md) | Demo runbook, script and Q&A |
| [docs/deployment.md](docs/deployment.md) | The production server and how to deploy to it |

## Known issues

Checked against the code on 2026-09-12.

- **The engine has no source code in git.** `backend/engine/` is restored
  bytecode, built for Python 3.13. Nobody can edit it, and on any other Python
  the API silently falls back to a thinner reference implementation.
  [docs/engine.md](docs/engine.md#status-bytecode-only).
- **Live and fixture modes disagree on Ana's gap.** The engine says $425.90,
  while the calibration and `mocks/` say $409.91. The runway date agrees.
  `mocks/engine_check.json` claims an exact match, but it is stale.
  [docs/engine.md](docs/engine.md#known-discrepancy-with-the-calibration).
- **Production runs mixed modes.** As last recorded, the server has no `.env`
  (so the agent is scripted) and no `frontend/.env.local`. Server-rendered
  pages therefore read fixtures, while browser calls under `/api/` reach
  FastAPI. [docs/deployment.md](docs/deployment.md#what-production-actually-serves).
- **`sync --source nessie` cannot reproduce the demo.** The sandbox ignores
  balance corrections. Always use the local cache.
  [docs/nessie-api-notes.md](docs/nessie-api-notes.md#balances-are-not-ours).
- **The web build ignores TypeScript errors** (`ignoreBuildErrors` in
  `frontend/next.config.mjs`). Run `npx tsc --noEmit` yourself.
- **The phone app has Jest configured but no tests yet.**

## Glossary

The project was built by a four-person team split by layer. Those labels survive
in code comments and some payloads:

| Label | Layer | Seen in |
|---|---|---|
| P1 | Data and Nessie integration (`backend/nessie`, `seed`) | `"_source": "P1 reference projection"` in fixtures |
| P2 | Engine (`backend/engine`) | `engine.from_p2` in `/api/health` |
| P3 | API and agent (`backend/api`, `backend/agent`) | `"_engine": "p3-reference"` when the fallback answers |
| P4 | Frontend, mobile, pitch | — |

Other terms: **runway date** is the first day checking is projected to drop
below the $100 safety buffer. **Gap** is how much money is missing to reach the
flight home. **Arming** means firing the scam and anomaly scenarios into the
cache.
