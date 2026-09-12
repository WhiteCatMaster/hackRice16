# EXTreasurer — frontend (P4)

The web app from [begin.md §7](../begin.md): dashboard with the runway chart,
bill decoder, credit builder, safety centre with the pre-transfer pause, and the
copilot with an approval gate in front of every write. The copilot will answer
with your own model key if you give it one — see [Your own model](#your-own-model).

## Run it

Node 20+ and pnpm (`npm i -g pnpm`).

```bash
pnpm install
pnpm dev        # http://localhost:3000
```

Over HTTPS instead:

```bash
pnpm dev:https  # https://localhost:3000
```

The certificate in `certificates/` is self-signed and only covers `localhost`,
`*.localhost`, `127.0.0.1` and `::1`, so the browser warns once and you accept
it. It is not committed — `pnpm cert` makes a fresh one (valid a year) if it is
missing or expired. Nothing outside your machine should ever trust it.

No API key, no backend, no network needed. With `TREASURER_API_BASE` unset the app
reads P1's fixtures from `../mocks`. If that folder is missing, generate it:

```bash
cd .. && python -m seed.reset_demo
```

Personas: `/?user=ana` (the demo), `/?user=raj`, `/?user=lucia`.

## Switching to the real backend

```bash
cp .env.example .env
# TREASURER_API_BASE=http://localhost:8000
```

That is the only change. The top bar says which mode you are in, so nobody
demos fixtures thinking they are live.

## How the data gets in

```
components/*  ──►  app/api/**/route.ts  ──►  lib/api.ts  ──┬─► P3's FastAPI   (TREASURER_API_BASE set)
(client)           (the contract, mirrored)                └─► ../mocks/*.json (otherwise)

app/page.tsx ─────────────────────────────────────────────► lib/api.ts (server, no HTTP hop)
```

`lib/contract.ts` types every endpoint in the §7 table. The routes under
`app/api` mirror those paths exactly, so a client component calls
`/api/transfers/check` whether or not P3 is up.

Three shapes the screens need that §7 does not define:

| Needs | Mock mode | Live mode |
|---|---|---|
| Recent activity | derived from `<persona>_snapshot.json` | `GET /api/users/{id}/activity`, empty if absent |
| Home city, arrival date | `<persona>_snapshot.json` → `customer` | `GET /api/users/{id}/profile`, header degrades if absent |
| "Can I afford $X?" | *nothing* — the card says so | `POST /api/users/{id}/affordability` |

The first two degrade instead of breaking. Affordability cannot: the answer
depends on the amount typed, so there is no fixture to pre-export and the card
asks for the backend rather than inventing a number.

## Your own model

The copilot's prose comes from whatever model the backend has a key for: one
key, in one `.env`, on one laptop. Anyone else opening this app has their own —
so **Copilot → Use your own key** takes it.

Three providers, because the backend speaks three (`GET /api/health` →
`agent.byok.accepted` is the live list): Google Gemini (`AIza…`), Claude
(`sk-ant-…`), and anything speaking OpenAI's chat-completions shape (`sk-…`) —
OpenAI itself, OpenRouter, Groq, or a model running on the machine with the
backend, via the optional endpoint field.

Where it goes: `lib/model-key.ts` keeps it in this browser's `localStorage`.
`app/api/chat/route.ts` copies it from the request to the backend as the
`X-Model-*` headers and forgets it — it is never read, logged or stored in that
hop — and the backend spends it on that one turn and keeps nothing
(`backend/agent/keys.py`). The phone does the same thing against its keystore.

Two things worth knowing before demoing it:

- **A key needs the backend.** The tools that produce every number live there, so
  in fixture mode a stored key has nothing to spend it — the panel says so.
- **A key that does not work is reported, not swallowed.** A typo, an empty
  quota, a model name that does not exist: the answer still arrives, composed by
  the backend's scripted router from the same tools, and the copilot says the key
  did not write it and why.

## What is honest about this UI

- **No number is computed here.** Balances, the runway date, the gap, the burn
  rate and every forecast point come from the engine through the API. The
  frontend formats and converts currency; that is all.
- **Fixture mode says so.** The status line in the top bar reads `RUNNING ON
  FIXTURES` until a backend is configured, and an approved action in fixture
  mode tells you nothing was written to Nessie.
- **Simulated fields are labelled.** The credit view prints whatever the
  backend puts in `_simulated`, because Nessie has no credit limit, APR or
  credit score.
- **The answer says who wrote it.** A reply composed with your own key says so
  under the bubble; one that fell back to the scripted router does not claim
  otherwise.

## Demo path (begin.md §9)

Arm the demo data first, or the Safety centre is empty in live mode:

```bash
cd .. && python -m seed.reset_demo --arm
```

1. Dashboard, `$` ↔ `€` toggle — the runway ends before the flight home.
2. **Runway** → *Your options* (what the engine would do about it, each with a
   measured effect) → *Can I afford it?* → type `47.34` → "Not yet", with the
   plan that turns it into a yes.
3. **Copilot** → the same question in words → the proposed action card →
   Approve. The dashboard behind it re-reads itself: the balance and the runway
   date actually move.
4. **Safety center** → *Send money* → the fake landlord transfer → the pause.
5. Same list, `Marta Aguirre` → goes through. That one matters: a check that
   stops everything is not a feature, and a judge will ask.

## Layout

```
app/
  page.tsx          server component; loads everything, renders the dashboard
  api/              the §7 contract, proxying to P3 or serving mocks/
  globals.css       the design system (warm paper, editorial type)
components/
  dashboard.tsx     the shell and the five views
  affordability.tsx "can I afford it?", answered by the engine
  forecast-chart.tsx  the runway line, drawn from the forecast series
  copilot.tsx       chat, proposed actions, the confirmation gate
  model-key.tsx     bring your own model key
  safety.tsx        alerts, the scenario runner, the pause modal
lib/
  contract.ts       every endpoint's response, as types
  api.ts            mocks-or-backend, the one switch
  format.ts         money, dates, percentages
  model-key.ts      the user's own model key, in this browser only
```
