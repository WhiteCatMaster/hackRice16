# Landed — frontend (P4)

The web app from [begin.md §7](../begin.md): dashboard with the runway chart,
bill decoder, credit builder, safety centre with the pre-transfer pause, and the
copilot with an approval gate in front of every write.

## Run it

```bash
pnpm install
pnpm dev        # http://localhost:3000
```

No API key, no backend, no network needed. With `LANDED_API_BASE` unset the app
reads P1's fixtures from `../mocks`. If that folder is missing, generate it:

```bash
cd .. && python -m seed.reset_demo
```

Personas: `/?user=ana` (the demo), `/?user=raj`, `/?user=lucia`.

## Switching to the real backend

```bash
cp .env.example .env
# LANDED_API_BASE=http://localhost:8000
```

That is the only change. The top bar says which mode you are in, so nobody
demos fixtures thinking they are live.

## How the data gets in

```
components/*  ──►  app/api/**/route.ts  ──►  lib/api.ts  ──┬─► P3's FastAPI   (LANDED_API_BASE set)
(client)           (the contract, mirrored)                └─► ../mocks/*.json (otherwise)

app/page.tsx ─────────────────────────────────────────────► lib/api.ts (server, no HTTP hop)
```

`lib/contract.ts` types every endpoint in the §7 table. The routes under
`app/api` mirror those paths exactly, so a client component calls
`/api/transfers/check` whether or not P3 is up.

Two shapes the screens need that §7 does not define:

| Needs | Mock mode | Live mode |
|---|---|---|
| Recent activity | derived from `<persona>_snapshot.json` | `GET /api/users/{id}/activity`, empty if absent |
| Home city, arrival date | `<persona>_snapshot.json` → `customer` | `GET /api/users/{id}/profile`, header degrades if absent |

Both degrade instead of breaking, so P3 can add them whenever.

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

## Demo path (begin.md §9)

1. Dashboard, `$` ↔ `€` toggle — the runway ends before the flight home.
2. **Copilot** → an affordability question → the proposed action card → Approve.
3. **Safety center** → *Send money* → the fake landlord transfer → the pause.
4. Same list, `Marta Aguirre` → goes through. That one matters: a check that
   stops everything is not a feature, and a judge will ask.

## Layout

```
app/
  page.tsx          server component; loads everything, renders the dashboard
  api/              the §7 contract, proxying to P3 or serving mocks/
  globals.css       the design system (warm paper, editorial type)
components/
  dashboard.tsx     the shell and the five views
  forecast-chart.tsx  the runway line, drawn from the forecast series
  copilot.tsx       chat, proposed actions, the confirmation gate
  safety.tsx        alerts, the scenario runner, the pause modal
lib/
  contract.ts       every endpoint's response, as types
  api.ts            mocks-or-backend, the one switch
  format.ts         money, dates, percentages
```
