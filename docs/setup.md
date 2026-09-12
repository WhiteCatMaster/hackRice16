# Setup

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | **3.13** | The engine ships as 3.13 bytecode. On another version the API still runs, on the reference fallback ([engine.md](engine.md#status-bytecode-only)). The data layer alone works on 3.11+ |
| Node | 20+ | Both apps |
| pnpm | any recent | Web app locally (`packageManager: pnpm@12.3.4`). The production server uses npm, which also works |
| npm | bundled with Node | Phone app. It must be npm, not pnpm: Metro expects nested installs |
| Expo Go or a simulator | SDK 57 | Phone app, optional |

## 1. The data and the API

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt   # fastapi, uvicorn, anthropic
cp .env.example .env                        # optional: Nessie and model keys
.venv/bin/python -m seed.reset_demo --arm
```

`reset_demo` generates the dataset, runs the consistency checks, and loads
`data/treasurer.db`. It refreshes `mocks/`, and `--arm` fires every scam
scenario. It prints Ana's numbers when done. Without `--arm` the Safety screen
is empty in live mode, while the fixtures show four alerts.

Start the API:

```bash
.venv/bin/uvicorn backend.api.app:app --port 8000 --reload
# or, with no third-party packages at all:
.venv/bin/python -m backend.api.serve 8000
```

Check it:

```bash
curl -s localhost:8000/api/health | python3 -m json.tool
```

Look at three fields:
- `engine.engine_module` should be `"backend.engine"`. `null` means you are on
  the fallback.
- `agent.mode` is `llm` or `scripted`.
- `cache` should show 480 purchases across 6 customers.

FastAPI also serves interactive docs at http://localhost:8000/docs.

## 2. The web app

```bash
cd frontend
pnpm install
echo 'TREASURER_API_BASE=http://127.0.0.1:8000' > .env.local   # omit to run on fixtures
pnpm dev                                                       # http://localhost:3000
```

Personas: `/?user=ana` (default), `/?user=raj`, `/?user=lucia`.

Over HTTPS, for testing clipboard or secure-context behaviour:

```bash
pnpm cert        # once: self-signed cert for localhost, valid a year, gitignored
pnpm dev:https   # https://localhost:3000
```

## 3. The phone app

```bash
cd mobile
npm install
cp .env.example .env    # set EXPO_PUBLIC_TREASURER_API_BASE=http://127.0.0.1:8000, or leave empty for fixtures
npm start               # i = iOS simulator, a = Android, w = web, or scan the QR with Expo Go
```

On a real phone, `127.0.0.1` is rewritten to the laptop's LAN address, the one
Metro served from. That only works if the API listens beyond loopback:

```bash
.venv/bin/uvicorn backend.api.app:app --host 0.0.0.0 --port 8000
```

The phone and laptop must be on the same network. The phone calls the API
directly (no proxy), and both servers already send permissive CORS headers.

## 4. Optional: a real model and real Nessie

Put keys in the root `.env` ([configuration.md](configuration.md)):

- `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` switches the copilot
  from scripted to a model. You can also paste a key into the copilot at
  runtime; nothing on the server needs to change ([agent.md](agent.md#bring-your-own-key)).
- `NESSIE_API_KEY` enables `seed.seed --push` and lets approved transfers reach
  Nessie. Read [nessie-api-notes.md](nessie-api-notes.md) before pushing: the
  sandbox has sharp edges.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `/api/health` shows `engine_module: null`, a warning in the log | Not running Python 3.13 | Recreate `.venv` with 3.13 |
| Safety screen empty in live mode | Scenarios not armed | `python -m seed.reset_demo --arm` |
| Web top bar says RUNNING ON FIXTURES | `TREASURER_API_BASE` unset, or the dev server started before you set it | Set it in `frontend/.env.local` and restart `pnpm dev` |
| Phone stays on fixtures | Variable missing the `EXPO_PUBLIC_` prefix, or Metro not restarted | Fix the name, then `npm start -- --clear` |
| Phone in live mode but every screen is empty | uvicorn bound to 127.0.0.1, or phone on another network | `--host 0.0.0.0`, same Wi-Fi |
| Metro cannot resolve `expo-secure-store` | Dependencies not installed | `npm install` (or `npx expo install expo-secure-store`) |
| Copilot replies say `_fell_back … HTTP 429` | Gemini free tier: 20 requests a day per model, one per tool round | Wait, use a paid key, or change `TREASURER_GEMINI_MODEL` |
| Numbers changed after `sync --source nessie` | The sandbox's balances are not the demo's | `python -m seed.reset_demo --arm` |
| Balances changed after rehearsing | Approving an action really moves money in the cache | `python -m seed.reset_demo --arm` |
| `Connection refused` to Nessie | Using `http://` | Nessie is HTTPS only |
