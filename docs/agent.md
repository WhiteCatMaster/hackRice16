# Agent

`backend/agent/`. It answers one chat message per call to
`loop.answer(conn, user, message, language=None, credential=None)`, served as
`POST /api/chat`.

| File | Role |
|---|---|
| `loop.py` | Chooses the provider, runs the tool loop per provider, and holds the scripted router, language detection and fallback handling |
| `tools.py` | The eleven tools, as a schema and a dispatcher. All data, no prose |
| `prompts.py` | System prompt and persona facts |
| `keys.py` | Parses and validates a user's own model key from request headers |
| `gemini.py` | Gemini `generateContent` over `urllib`: schema translation, thinking settings, one POST |
| `openai_compat.py` | OpenAI chat-completions over `urllib`, for any compatible endpoint |

## Two modes

- **`llm`**: a model reads the system prompt, calls tools, and writes the
  reply. There are at most 6 tool rounds per turn; Claude gets 1,024 output
  tokens, and HTTP calls time out after 45 seconds.
- **`scripted`**: no model, no network. Keyword routing picks the same tools
  and formats a reply from the same numbers, in English or Spanish. This is not
  a toy: it answers every demo question with real numbers, and it is what runs
  when an API is down.

## Choosing a provider

Evaluated on every turn, in this order:

1. **A key the request brought** (`X-Model-*` headers) wins over everything,
   including `TREASURER_PROVIDER`. If this backend cannot speak that provider
   (Anthropic without its SDK), the turn is scripted and marked
   `_key_rejected`.
2. **`TREASURER_PROVIDER`** forces `gemini`, `anthropic`, `openai` or
   `scripted`. A forced provider without a key is scripted.
3. Otherwise **the first key present**: `GEMINI_API_KEY`, then
   `ANTHROPIC_API_KEY` (and the `anthropic` package), then `OPENAI_API_KEY`.
4. Otherwise **scripted**.

Gemini and OpenAI-compatible providers use only `urllib`. Anthropic uses the
official SDK. Each has its own loop in `loop.py`, because the wire formats
differ:

- Gemini tool calls arrive as `functionCall` parts, and results return as
  `functionResponse` parts in a user turn.
- OpenAI returns `tool_calls` on the assistant message, and results go back as
  `role: "tool"` messages.

All three call the same `tools.run()`.

`openai` means the API shape, not the company. Set `OPENAI_BASE_URL` (or send
`X-Model-Base-URL`) and it talks to OpenRouter, Groq, Together, vLLM, or Ollama
on the same machine.

## Tools

| Tool | Engine call | Notes |
|---|---|---|
| `get_summary` | `summary` | |
| `get_forecast` | `forecast` | The daily `series` is stripped: it is for charts, not the model's context |
| `check_affordability` | `affordability` | `amount` required, `when` optional |
| `get_bills` | `bills` | |
| `get_credit` | `credit` | |
| `get_activity` | `activity` | `limit`, default 8 |
| `get_alerts` | `alerts` | |
| `check_transfer` | `check_transfer` | The prompt requires this before helping with any payment to someone new |
| `suggest_fixes` | `suggest_fixes` | |
| `propose_transfer` | `actions.propose` | Stages an approval card. **Does not move money** |
| `propose_spending_cap` | `actions.propose` | Estimates savings from the last 30 days of category spend |

## What the system prompt enforces

`prompts.SYSTEM`, filled in with the persona's name, home city, arrival and
flight dates, language and today's date:

- **Never calculate.** Every number must be quoted from a tool result in this
  conversation. The rule also covers what goes *into* tools: if the user never
  gave a price, ask for it. Do not invent one for `check_affordability` to
  price.
- Answer in the persona's language unless the user writes in another one.
- Be short: two or three sentences, then the number that matters. Plain text,
  because the chat bubble does not render markdown. Write money as `$425.90`,
  never field names.
- Explain US money concepts plainly: utilization, statement balance, SSN,
  overdraft fees.
- **Never move money; only propose.** When something is not affordable, call
  `suggest_fixes` and propose the fix in the same turn. Calling the tool *is*
  asking. Quote the measured effect, not the advertised one.
- If `check_transfer` pauses, do not help complete the payment. Explain the
  reasons and ask its questions.
- Mention in passing when a figure is simulated (limits, score estimates,
  freezes, FX, caps).

Two safeguards sit outside the prompt:

- **Language is detected in code.** `detect_language()` decides from the message
  (Spanish punctuation, accents and common words) before the model sees it. The
  persona's language is only the fallback.
- **Backstop proposal.** If the model called `suggest_fixes`, described a
  transfer, and never called `propose_transfer`, `_backstop_proposal()` stages
  the engine's in-plan transfer anyway. Two Gemini models were observed ending
  turns with "I have prepared a proposal" and no card. This stages a card and
  does not move money: approval is still required.

## The scripted router

`_scripted()` matches the lowercased message against keyword lists in
`loop.WORDS` (English and Spanish), in this order:

| Intent | Example triggers | Tools |
|---|---|---|
| afford | afford, permitir, trip, viaje, buy, comprar, cost | `get_summary`, `check_affordability`, and `suggest_fixes` + `propose_transfer` when the answer is no. With no amount in the message it asks for one |
| fixes / transfer | help, ayuda, what should, gap, run out, move, transferir | `suggest_fixes`, `propose_transfer` |
| alerts | alert, fraud, scam, estafa | `get_alerts` |
| credit | credit, tarjeta, score, utilization | `get_credit` |
| bills | bill, factura, rent, alquiler, trial | `get_bills` |
| activity | spent, gasté, recent, movimiento | `get_activity` |

For English affordability answers it quotes the engine's own `reason` text
verbatim. That text is English-only, so Spanish uses the router's templates.

## Bring your own key

Anyone can use their own model key without touching the server: a judge, a
teammate, a phone on another network. `POST /api/chat` reads these headers:

| Header | Value |
|---|---|
| `X-Model-Key` | The key |
| `X-Model-Provider` | `gemini`, `anthropic` or `openai`. Optional: inferred from `sk-ant-` → anthropic, `AIza` → gemini, `sk-` → openai |
| `X-Model-Name` | Optional model name, e.g. `gemini-3-flash`, `llama3.1:8b` (max 120 chars) |
| `X-Model-Base-URL` | `openai` only. Must be `https`, or `http` to `localhost`/`127.0.0.1`/`::1` |

```bash
curl -s localhost:8000/api/chat -H 'content-type: application/json' \
  -H "X-Model-Key: $GEMINI_API_KEY" \
  -d '{"user":"ana","message":"What should I do?"}' | python3 -m json.tool
```

**Nothing keeps the key.** `keys.from_headers()` builds a frozen `Credential`
with a redacted `repr`; the turn uses it and drops it. There is no disk, no
SQLite, no log line. Headers are used instead of the body because bodies are
what end up echoed in error messages. Neither transport puts the key in a URL:
Gemini receives it as `X-goog-api-key`, OpenAI as `Authorization`. Only the
client remembers it:

- web: `localStorage` via `frontend/lib/model-key.ts`
- phone: the OS keystore via `mobile/lib/secrets.ts`

Two failure modes, handled differently on purpose:

| Problem | Response |
|---|---|
| **Unreadable**: empty, longer than 400 chars, whitespace or non-ASCII, unknown provider, provider not inferable, base URL on a non-openai provider, plain-http remote endpoint | `400 bad_model_key` with a message saying what is wrong |
| **Readable but does not work**: typo, no quota, nonexistent model, provider unsupported here | `200` from the scripted router, with `_key_rejected: true` and `_fell_back` holding the provider's own message (extracted, max 180 chars) |

`/api/health` exposes `agent.byok.accepted` and `agent.byok.headers`, so a
settings screen can be built from the server's answer.

## Failures and fallbacks

Any exception in a model turn (HTTP error, timeout, rate limit) is logged and
answered by the scripted router. The reply says so in `_fell_back`, and
`_provider` reads `scripted`, so the UI never credits a model with the router's
words.

**Gemini free tier:** 20 requests per day per model, and one chat turn spends
one request per tool round. Expect `_fell_back: "HTTP 429: You exceeded your
current quota…"` after a few turns. The answer is still correct, in the router's
phrasing.

## The chat fixture

`mocks/api_chat_response.json` is what both apps show for chat in fixture mode,
and therefore in any backup video. It is generated, not hand-written:

```bash
python -m seed.export_chat_fixture   # asks the §9 question as Ana, with whatever provider is configured
```

Regenerate it after anything that changes the answer: data, engine text, the
router. `tests/test_api.py::TestChatFixture` fails if the fixture and the live
agent disagree on language or on whether an action is proposed. The action id
is pinned to `act_demo_transfer`.
