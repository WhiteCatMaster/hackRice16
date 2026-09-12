# Configuration

Three independent environment files. None are committed; each has a documented
`.env.example` next to where it goes.

| File | Read by | Loaded how |
|---|---|---|
| `.env` (repo root) | Everything in Python: data layer, engine, API, agent | `backend/nessie/config.py` parses it by hand at import. **A variable already set in the real environment wins over the file** |
| `frontend/.env.local` | The Next.js server | Next.js, at `pnpm dev` / `next start`. Restart after changing it. `frontend/.env` also works |
| `mobile/.env` | The Expo bundle | Expo inlines `EXPO_PUBLIC_*` variables at bundle time. Restart Metro after changing it |

## Root `.env`

### Nessie and data

| Variable | Default | Meaning |
|---|---|---|
| `NESSIE_API_KEY` | empty | Needed only to write to Nessie (`seed --push`, approved transfers). Reads work without it. The placeholder `put_your_key_here` counts as unset |
| `NESSIE_BASE_URL` | `https://api.nessieisreal.com` | HTTPS only; `http://` is refused at the TCP level |
| `TREASURER_DB` | `data/treasurer.db` | SQLite cache. A relative path resolves from the repo root |
| `DEMO_AS_OF` | today | The date the demo treats as "today", as `YYYY-MM-DD`. All history, bills and flight dates are generated relative to it |
| `DEMO_RANDOM_SEED` | `20260911` | Same seed gives a byte-identical dataset |

### Copilot model

With no key at all the agent uses its scripted router; the demo works either
way. A key sent by the user with a request overrides all of these for that turn
([agent.md](agent.md#bring-your-own-key)).

| Variable | Default | Meaning |
|---|---|---|
| `TREASURER_PROVIDER` | empty | `gemini`, `anthropic`, `openai` or `scripted`. Forces one provider; if that provider has no key, the agent answers scripted. Unset means the first provider with a key, in the order Gemini, Anthropic, OpenAI |
| `GEMINI_API_KEY` | empty | Google AI Studio key |
| `TREASURER_GEMINI_MODEL` | `gemini-flash-latest` | |
| `GEMINI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta` | |
| `ANTHROPIC_API_KEY` | empty | Requires the `anthropic` package (in `requirements.txt`) |
| `TREASURER_MODEL` | `claude-sonnet-5` | Claude model |
| `OPENAI_API_KEY` | empty | OpenAI, or any service that speaks its chat-completions API |
| `TREASURER_OPENAI_MODEL` | `gpt-4o-mini` | |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Point at OpenRouter, Groq, vLLM, Ollama… |

`.env` is loaded once when the API starts, so restart it after editing the file.
Which provider answers is then decided per turn from whatever keys are present.

## `frontend/.env.local`

| Variable | Default | Meaning |
|---|---|---|
| `TREASURER_API_BASE` | empty | The API, e.g. `http://127.0.0.1:8000`. **Empty means fixture mode**: every screen reads `mocks/` |
| `TREASURER_MOCKS_DIR` | `../mocks` | Where fixtures are read from, relative to `frontend/` |
| `TREASURER_USER` | `ana` | Persona when the URL has no `?user=` |

## `mobile/.env`

| Variable | Default | Meaning |
|---|---|---|
| `EXPO_PUBLIC_TREASURER_API_BASE` | empty | The API. Empty means fixture mode, using fixtures bundled from `../mocks`. A loopback host is rewritten to the Metro host's LAN address on native |
| `EXPO_PUBLIC_TREASURER_USER` | `ana` | Persona on launch; the header switches between all three |

The `EXPO_PUBLIC_` prefix is required. Without it the variable is `undefined` on
the phone, and the app stays in fixture mode without an error.

## Command-line overrides

Most seed scripts take `--as-of YYYY-MM-DD`, which overrides `DEMO_AS_OF` for
that run. See [data-layer.md](data-layer.md#commands).
