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
curl -s 'localhost:8000/api/health?probe=1'        # also asks Nessie
```

`/api/health` names, per capability, whether **P2's engine** or **P3's reference
projection** answered, and whether the agent is running on a **model**
(and which one) or its **scripted router**. Nothing else in the app has to guess.

`?probe=1` adds a live Nessie check through `NessieClient.check_access()`, which
reports `{reachable, authorized, detail}`. It is opt-in because it makes a network
call: reads on Nessie are ungated but writes need a valid key, so a bare
`key_present` tells you nothing useful, and a health endpoint that can hang is
worse than one that admits it did not check. A dead Nessie never makes the API
report itself unhealthy.

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
| POST | `/api/chat` | `{user, message, language?}` → reply + optional proposed action. Reads a brought-along model key off the headers — see [below](#using-your-own-key) |
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

> **It imports again, from bytecode.** `backend/engine/` still has no source —
> the `.py` files were lost and were never committed to any branch. What survived
> was the compiled output, so the ten modules are restored as sourceless `.pyc`
> next to where their source belongs, which Python imports directly. All twelve
> capabilities resolve to `backend.engine` and payloads say
> `"_engine": "backend.engine"`.
>
> Two things follow. The bytecode is built for **one** Python version (3.13, what
> `.venv` runs); on any other the import fails and the port falls back to the
> reference with a warning in the log — so check `engine_module` in
> `/api/health` before a demo rather than assuming. And nobody can edit the
> engine until someone recommits the source from the machine that still has it.
> `*.pyc` is in `.gitignore`, so these files need `git add -f` to be tracked at
> all; treat the copy in git as a hedge, not a substitute for the source.

The reference is not a competing engine, and it is not a forecast: it reads the
generator's own calibrated burn rate, which by P2's standard is grading its own
homework. That is the right trade for what it is — a stand-in whose one job is to
reproduce P1's published numbers, asserted field by field and persona by persona
in `TestReferenceMatchesCalibration` — so the API answered before the engine
landed and still answers if a change breaks it mid-event — which is the situation
it is holding up today. Every number the app shows comes from `backend.engine`
whenever it is importable; check `/api/health` rather than assuming.

What the reference costs, for when it is the one answering: it does not return
`already_short` or `max_safe_through` on affordability, nor `days_gained` on a
fix's effect, so the screens that want those drop to their less precise branch and
five tests in `tests/test_integration.py` fail. Those five were one missing
module, not five bugs — they pass with the engine loaded, and they are the check
that says whether it really is.

One hook the reference has and P2's forecast does not yet:

```python
forecast(conn, user, target=None, extra_events=[{"date": ..., "amount": ..., "label": ...}])
```

Signed amounts, merged into the projection like any scheduled event. It is what
measures an action's before/after. `engine_port.accepts("forecast", "extra_events")`
reports whether the live engine takes it.

### A note on rounding, and a warning about diagnosing with it

The reference rounds only on the way into `series`, and tracks `min_balance` and
`runway_date` off the unrounded value. Rounding the *running* balance instead
loses a fraction of a cent per step, and over a ~50-day projection that is enough
to move the runway date by a day when the balance is calibrated to land just
under the buffer. `test_rounding_does_not_drift` asserts the stepped balance
equals the same balance computed in one shot.

Worth recording how that theory was misapplied. P3's reference and P2's engine
disagreed by one day on Ana, and this was diagnosed — by me — as that rounding
bug in the engine. It was not. Holding the projection fixed and varying only the
burn rate reproduced each side's numbers exactly: the engine measures the rate
from the transactions, while P1's generator projected from the knob it had solved
for, and the two differed in the fourth decimal place. Same arithmetic, different
input. P1 has since retuned so the measured rate and the solved knob agree.

The lesson for anyone chasing the next one-day disagreement: vary one input at a
time against a fixed projection before blaming the projection. `_project()` takes
the burn rate through `daily_burn()`, so this is a two-line experiment.

## The agent

Two modes, chosen by whether there is a model key.

- **llm** — a model with eleven tools, up to six tool-calling turns. If the API
  errors or is throttled mid-demo it falls back to the scripted router and says so
  in `_fell_back`.
- **scripted** — no key, no network. Routes the question to the same tools by
  keyword and formats the answer from the same numbers.

Three providers answer to the **llm** contract, and `/api/health` names the live
one in `agent.provider`:

| Provider | Key | Model setting |
| --- | --- | --- |
| `gemini` | `GEMINI_API_KEY` | `TREASURER_GEMINI_MODEL` (default `gemini-flash-latest`) |
| `anthropic` | `ANTHROPIC_API_KEY` | `TREASURER_MODEL` (default `claude-sonnet-5`) |
| `openai` | `OPENAI_API_KEY` | `TREASURER_OPENAI_MODEL` (default `gpt-4o-mini`), `OPENAI_BASE_URL` |

`TREASURER_PROVIDER` pins one; unset, whichever key is present answers, Gemini
first. Each speaks a different wire shape, so each has its own turn loop in
`loop.py` and its own transport: Gemini's tool calls arrive as `functionCall`
parts and results go back as `functionResponse` parts in a *user* turn; OpenAI's
arrive as `tool_calls` on the assistant message and each result goes back as its
own `role: "tool"` message. All three loops call the same `tools.run`, so a tool
never learns which model asked. Both transports are urllib, not a new dependency:
`requirements.txt` installs nothing that the fallback needs.

`openai` is the chat-completions *shape*, not only OpenAI. With `OPENAI_BASE_URL`
(or the per-request header below) it is also OpenRouter, Groq, Together, vLLM or a
model running on the same laptop — one transport, several favourite models.

Gemini's free tier is 20 requests a day per model, and one chat turn spends one
per tool round. Expect `_fell_back` with an HTTP 429 once that runs out — the
answer is still correct, it is just the router's phrasing. A paid key, or a
lighter model in `TREASURER_GEMINI_MODEL`, buys more room.

All three answer in the language the question was asked in (`detect_language`),
not merely the persona's own, and all return `used_tools` and any
`proposed_action`.

## Using your own key

Everything above configures *this* server's key. A judge, a teammate on a train
or a phone on someone else's wifi has their own key and no way to put it in our
`.env` — so `POST /api/chat` accepts one per request:

| Header | |
| --- | --- |
| `X-Model-Provider` | `gemini`, `anthropic` or `openai`. Optional: inferred from `sk-ant-`, `AIza`, `sk-` |
| `X-Model-Key` | the key |
| `X-Model-Name` | optional model, e.g. `gemini-3-flash`, `llama3.1:8b` |
| `X-Model-Base-URL` | `openai` only: an OpenAI-compatible endpoint. https, or http to localhost |

```bash
curl -s localhost:8000/api/chat \
  -H 'content-type: application/json' \
  -H "X-Model-Key: $GEMINI_API_KEY" \
  -d '{"user":"ana","message":"What should I do?"}' | python -m json.tool
```

A key sent this way beats `TREASURER_PROVIDER` and the server's own keys: the
person asking pasted it in to be used, and quietly billing somebody else instead
would be the wrong answer given silently.

**Nothing keeps it.** `backend/agent/keys.py` parses the headers into a
`Credential`, the turn spends it, and it is gone — no disk, no sqlite, no log
line, and a redacted `__repr__` so it cannot reach a traceback either. The device
that sent it is the only thing that remembers: `localStorage` in the browser
(`frontend/lib/model-key.ts`), the phone's keystore on a device
(`mobile/lib/secrets.ts`). Headers rather than the body because a body is the
thing most likely to be echoed into a debug print, and neither transport puts a
key in a URL — Gemini takes `X-goog-api-key`, OpenAI takes `Authorization`.

Every reply says who answered it, so the copilot can stop claiming a model wrote
something the router did:

| Field | |
| --- | --- |
| `_provider` | `gemini`, `anthropic`, `openai`, or `scripted` |
| `_key_source` | `user`, `server`, or `null` when no model answered |
| `_fell_back` | why the model path was abandoned, when it was |
| `_key_rejected` | true when the *brought-along* key is the reason — the user's to fix |

Two failure modes, deliberately different. A key this backend cannot read at all
is `400 bad_model_key` with a message saying which way it is unreadable ("A key
has no spaces or line breaks in it"). A key that reads fine but does not work — a
typo, an empty quota, a model name that does not exist, a provider this backend
has no SDK for — answers `200` from the scripted router with `_key_rejected: true`,
because a wrong answer is worse than a plain one and no answer is worse than both.

`/api/health` carries `agent.byok.accepted` (the providers this build can speak;
`anthropic` drops out where its SDK is missing) and `agent.byok.headers`, so a
settings screen can be built from the answer rather than from a guess.

Where the engine writes its own explanation — `affordability().reason` does, and
it is written from the numbers it just computed — the scripted router quotes it
rather than re-templating. That text is English-only today, so Spanish still goes
through the router's own phrasing. If the engine gains translated reasons, drop
the language check in `_scripted`.
The scripted router answers every §9 demo question with real numbers. That is
deliberate: an LLM API is one more thing that can be down at 9 a.m. on stage.

## Tests

```bash
python -m unittest discover tests      # P1, P2 and P3
python -m unittest tests.test_api      # this layer
```

### The chat fixture

`mocks/api_chat_response.json` is what P4 renders when the backend is down, which
is also the backup-video path. P1's exporter seeds it only if missing and never
overwrites it, so keeping it truthful is P3's job:

```bash
python -m seed.export_chat_fixture
```

Run it whenever the reply changes — a retuned dataset, a new engine `reason`, a
change to the router. `TestChatFixture` fails if the committed fixture and the
live agent disagree about the language or about whether an action is proposed. It
previously answered "Sí, puedes ir" where the live agent answers "Ahora mismo no",
which would have put two different answers on stage depending on the laptop's mode.

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
  loop.py         provider choice, the two tool loops, the scripted router
  gemini.py       Gemini transport: schema translation and one POST
tests/test_api.py
```
