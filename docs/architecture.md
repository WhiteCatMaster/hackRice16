# Architecture

## The shape of it

```
                       ┌──────────────────────────┐
                       │  Nessie API (mock bank)  │  https://api.nessieisreal.com
                       └────────────▲─────────────┘
                   seed.seed --push │ sync --source nessie (not for demos)
                       ┌────────────┴─────────────┐
 seed/generator.py ───►│  SQLite cache            │  data/treasurer.db
 (deterministic data)  │  backend/nessie/db.py    │  Nessie mirror + our own fields
                       └────────────┬─────────────┘
                                    │ backend/nessie/repo.py  (every read goes through here)
               ┌────────────────────┼──────────────────────┐
     ┌─────────▼─────────┐  ┌───────▼────────┐   ┌─────────▼─────────┐
     │ backend/engine    │  │ backend/agent  │   │ backend/api/      │
     │ forecast, fixes,  │◄─┤ model + tools, │   │ actions.py        │
     │ affordability,    │  │ or scripted    │──►│ confirmation gate │
     │ risk, anomalies   │  │ router         │   │ (only write path) │
     └─────────▲─────────┘  └───────▲────────┘   └─────────▲─────────┘
               │ engine_port.py     │                      │
               │ (falls back to     │                      │
               │  reference.py)     │                      │
     ┌─────────┴────────────────────┴──────────────────────┴─────────┐
     │  backend/api/handlers.py  — plain functions, no web framework │
     │  app.py (FastAPI)  or  serve.py (standard library)            │
     └───────────────────────────────▲───────────────────────────────┘
                                     │ JSON over HTTP, port 8000
             ┌───────────────────────┴────────────────────────┐
   ┌─────────┴──────────┐                          ┌──────────┴─────────┐
   │ frontend/ (Next)   │                          │ mobile/ (Expo)     │
   │ server → lib/api.ts│                          │ lib/api.ts calls   │
   │ browser → app/api/*│                          │ the API directly   │
   │ proxy routes       │                          │                    │
   └─────────┬──────────┘                          └──────────┬─────────┘
             └──────── no API base configured → mocks/*.json ─┘
```

## Layers

**Data** (`backend/nessie`, `seed`). A deterministic generator builds three
personas with about three months of history. The history is calibrated so the
demo tells a specific story. It is loaded into SQLite, optionally pushed to
Nessie first. `repo.py` is the read API. Nothing in this layer needs a
third-party package. [data-layer.md](data-layer.md)

**Engine** (`backend/engine`). Pure functions over the cache: `summary`,
`forecast`, `affordability`, `suggest_fixes`, `check_transfer`, `alerts`, and so
on. They return dictionaries already shaped like the API contract.
[engine.md](engine.md)

**API** (`backend/api`). `handlers.py` holds every route as a function returning
`(status, dict)`. Two thin wrappers serve it: `app.py` with FastAPI, and
`serve.py` with the standard library. `engine_port.py` routes each capability to
the engine or, if the engine cannot import, to `reference.py`. `actions.py` is
the confirmation gate. [api.md](api.md)

**Agent** (`backend/agent`). One chat turn: pick tools, call them, and write
prose from the results. It runs on Gemini, Claude or an OpenAI-compatible model.
With no working key it uses a keyword router over the same tools.
[agent.md](agent.md)

**Clients** (`frontend`, `mobile`). Both render the same screens from the same
typed contract (`lib/contract.ts`, byte-identical in both apps). Both switch
between the live API and `mocks/` with a single environment variable.
[frontend/README.md](../frontend/README.md), [mobile/README.md](../mobile/README.md)

## Three request paths

**A read** (dashboard, runway, bills, credit, alerts). The client calls
`GET /api/users/{id}/…`. The handler checks the persona exists, and
`engine_port.call()` runs the engine function against the cache. The response
carries `_engine`, which names who computed it. Nessie is never contacted.

**A chat turn.** `POST /api/chat` arrives with an optional model key in
`X-Model-*` headers. `loop.answer()` picks a provider, gives the model the system
prompt and eleven tools, and runs up to six tool rounds. It returns `reply`,
`used_tools`, and possibly a `proposed_action`. A proposed action is *staged*:
`actions.propose()` measures its effect on the runway and stores it in memory.
Nothing moves.

**A write.** The user taps Approve, and the client posts
`POST /api/actions/{id}/confirm`. `actions.confirm()` updates balances in the
cache, then best-effort writes the transfer to Nessie. It re-runs the forecast
and returns `runway_date_after` and `executed_in_nessie`. The client reloads
every screen, so the runway visibly moves.

## Design rules and where they live

These come from `begin.md` §6.

| Rule | Enforced by |
|---|---|
| **The model never calculates numbers.** It picks tools and explains results | `backend/agent/prompts.py` (system prompt), `tools.py` (tools return data, never prose). `used_tools` is on every reply |
| **Every write needs user confirmation** | `backend/api/actions.py` is the only code that changes a balance. Tools can only call `propose()`. `test_the_agent_cannot_move_money` |
| **The demo never depends on Nessie being live** | Every read goes through the SQLite cache. Nessie writes are best-effort. `seed.reset_demo` restores state in about a second |
| **Be honest about simulations** | `_simulated` field lists on payloads. `executed_in_nessie: false` whenever a write stayed local. The UIs print both |

## What degrades, and to what

| If this fails | This takes over | How you notice |
|---|---|---|
| Nessie is slow or down | The local cache, which every read already uses | Nothing changes. `/api/health?probe=1` reports it |
| Nessie rejects a write, or there is no key | The cache is updated anyway | `executed_in_nessie: false` on the action result |
| `pip install` failed, no FastAPI | `python -m backend.api.serve 8000`, same routes | Log banner says "stdlib mode" |
| The engine will not import (wrong Python) | `backend/api/reference.py`, per function | `_engine: "p3-reference"`, `/api/health` → `engine.engine_module: null`, a warning in the log |
| The model API errors or is rate-limited | The scripted router, same tools | `_fell_back` on the reply, `_provider: "scripted"` |
| A user's own key is bad | The scripted router | `_key_rejected: true`, shown in the copilot |
| No backend configured in a client | `mocks/*.json` | "RUNNING ON FIXTURES" (web) or the header status (phone) |

## What is simulated

Nessie has no concept of these, so they are stored in SQLite and labelled in
payloads:

- credit limit, APR, statement day, utilization
- card freeze
- intra-day timestamps
- merchant risk tags
- fraud and scam labels
- home currency and exchange rate
- known-payee history
- which payee a transfer went to
- spending caps

Details: [nessie-api-notes.md](nessie-api-notes.md#things-nessie-has-no-concept-of).
