# The API and the agent (P3) — handoff

Written for P2, P4 and whoever is answering questions at the table. What runs,
what it answers, and which parts are honest about being simulated.

## Run it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.api.app:app --port 8000 --reload
```

No FastAPI? The same routes, from the standard library:

```bash
python -m backend.api.serve 8000
```

Both serve identical JSON, because both are thin wrappers over
`backend/api/handlers.py`, which imports no web framework. P1 kept the data layer
dependency-free so a failed `pip install` could not kill the demo; this keeps that
property for the API.

Check what is live:

```bash
curl -s localhost:8000/api/health | python -m json.tool
```

`/api/health` names, per capability, whether **P2's engine** or **P3's reference
projection** answered, and whether the agent is running on **Claude** or its
**scripted router**. Nothing else in the app has to guess.

## Endpoints

Everything P4 calls, plus four that are useful at the table.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | Which engine, which agent mode, cache counts |
| GET | `/api/users/{id}/summary` | Balances, runway date, target date, gap |
| GET | `/api/users/{id}/forecast?target=` | Daily series + events. `target` optional |
| GET | `/api/users/{id}/bills` | Bills with plain-language explanations |
| GET | `/api/users/{id}/credit` | Balance, limit, utilization, suggested payment |
| GET | `/api/users/{id}/alerts` | Open scam and card-anomaly alerts |
| GET | `/api/users/{id}/activity?limit=` | Recent movements, newest first, signed amounts |
| GET | `/api/users/{id}/profile` | Home city, arrival, flight home |
| GET | `/api/users/{id}/fixes` | Candidate actions, each with its measured effect |
| GET | `/api/scenarios` | The seeded scam/anomaly cases |
| POST | `/api/users/{id}/affordability` | `{amount, when?}` → new runway date, safe maximum |
| POST | `/api/transfers/check` | `{user, scenario}` or `{user, amount, payee_id?, description?}` |
| POST | `/api/chat` | `{user, message, language?}` → reply + optional proposed action |
| POST | `/api/actions/propose` | Stage an action without going through chat |
| POST | `/api/actions/{id}/confirm` | `{user, action}` → the only write path |

Unknown persona is `404 unknown_user`. Bad input is `400`, never a `500`.

## The two design rules this layer enforces

**The LLM never calculates.** Every tool in `backend/agent/tools.py` returns data
from P2's engine or P1's cache. The model picks tools and writes prose; it is told
in the system prompt that any number not in a tool result is one it may not say.
`used_tools` comes back on every chat reply so the trace is visible on screen —
that is the cheapest possible answer to "how do you stop it hallucinating numbers?"

**Every write needs confirmation.** `backend/api/actions.py` is the only module
that moves money. Chat can only *propose*; the proposal gets an id and sits in
memory until `POST /api/actions/{id}/confirm` arrives. `test_the_agent_cannot_move_money`
asserts that asking the agent to move $500 changes no balance.

## Being honest about simulations

`executed_in_nessie` is `false` whenever the write only reached the local cache —
no API key, Nessie refused, or the action has no Nessie equivalent (spending caps,
card freezes). P4 prints that flag. It says `false` rather than something
flattering, deliberately.

Proposed actions carry `effect.measured`. When the live engine's `forecast()`
cannot model a hypothetical event, the effect is measured with P3's reference
projection and labelled `measured_by: "p3-reference"` — with the *before* taken
from the same projection, so the two dates on the approval card come from one
engine rather than two. If it cannot be measured at all, `runway_date_after` is
`null` and `measured_note` says why. An approval card that shows an unchanged date
for an action that does help is a wrong number in front of a judge.

## The seam with P2

`backend/api/engine_port.py` resolves each capability to `backend.engine` if it
has one and `backend/api/reference.py` otherwise, **per function, re-checked every
call**. P2's engine takes over the moment it imports; nothing restarts.

The reference is not a competing engine. It reproduces P1's published calibration
exactly — all four fields for all three personas, asserted in
`TestReferenceMatchesCalibration` — and exists so the API is demo-ready before P2
lands and still works if a change breaks the engine mid-event.

One hook the reference has and P2's forecast does not yet:

```python
forecast(conn, user, target=None, extra_events=[{"date": ..., "amount": ..., "label": ...}])
```

Signed amounts, merged into the projection like any scheduled event. It is what
measures an action's before/after. `engine_port.accepts("forecast", "extra_events")`
reports whether the live engine takes it.

### A note on rounding

Round the *running* balance each day and Ana's runway date moves from 2026-10-10
to 2026-10-11. The daily discretionary figure is 13.7614; rounding it to 13.76
every day loses $0.07 over the 51-day projection, which is enough to keep her at
or above the $100 buffer for one more day. Round only on the way into `series`,
and track `min_balance` and `runway_date` off the unrounded value.
`test_rounding_does_not_drift` pins it.

## The agent

Two modes, chosen by whether `ANTHROPIC_API_KEY` is set.

- **llm** — Claude with eleven tools, up to six tool-calling turns. If the API
  errors or is throttled mid-demo it falls back to the scripted router and says so
  in `_fell_back`.
- **scripted** — no key, no network. Routes the question to the same tools by
  keyword and formats the answer from the same numbers.

Both answer in the language the question was asked in (`detect_language`), not
merely the persona's own, and both return `used_tools` and any `proposed_action`.

Where the engine writes its own explanation — `affordability().reason` does, and
it is written from the numbers it just computed — the scripted router quotes it
rather than re-templating. That text is English-only today, so Spanish still goes
through the router's own phrasing. If the engine gains translated reasons, drop
the language check in `_scripted`.
The scripted router answers every §9 demo question with real numbers. That is
deliberate: an LLM API is one more thing that can be down at 9 a.m. on stage.

## Tests

```bash
python -m unittest discover tests      # 119 tests across P1, P2 and P3
python -m unittest tests.test_api      # 53 for this layer
```

`TestHttpRoutes.test_the_full_demo_path` walks §9 in order over real HTTP:
dashboard → Spanish chat → approve the fix → runway moves out → the fake landlord
pauses → the real roommate does not.

## Layout

```
backend/api/
  handlers.py     routes as plain functions; no web framework
  app.py          FastAPI wrapper
  serve.py        the same routes on http.server
  engine_port.py  the seam with P2; per-capability resolution
  reference.py    P3's stand-in engine, matching P1's calibration
  actions.py      the confirmation gate — the only write path
backend/agent/
  prompts.py      system prompt and persona context
  tools.py        eleven tools, all data, none of them execute
  loop.py         Claude tool loop, and the scripted router
tests/test_api.py
```
