# EXTreasurer web app

Next.js 16 (App Router), React 19, Tailwind 4. The screens:

- **Overview**: balances in dollars or the home currency, the runway, upcoming
  bills, alerts.
- **Runway**: the projection chart, the engine's fixes, "Can I afford it?".
- **Bills**: every bill explained, trial warnings.
- **Credit**: utilization and how US credit scoring works.
- **Safety**: alerts, a *Send money* scenario runner, the pre-transfer pause.
- **Copilot**: chat with approval cards, and *Use your own key*.

## Run

Node 20+ and pnpm.

```bash
pnpm install
pnpm dev            # http://localhost:3000
pnpm dev:https      # https://localhost:3000; run `pnpm cert` once first
pnpm build && pnpm start
```

Personas: `/?user=ana` (default), `/?user=raj`, `/?user=lucia`.

## Two modes, one variable

```bash
# frontend/.env.local
TREASURER_API_BASE=http://127.0.0.1:8000
```

| `TREASURER_API_BASE` | Data comes from | Top bar |
|---|---|---|
| unset | `../mocks/*.json`, read at request time | **RUNNING ON FIXTURES** · mocks/ · as of … |
| set | The API ([docs/api.md](../docs/api.md)) | Live |

Restart the dev server after changing it. Also available: `TREASURER_MOCKS_DIR`
(default `../mocks`) and `TREASURER_USER` (default `ana`).
[docs/configuration.md](../docs/configuration.md#frontendenvlocal)

What fixture mode cannot do:

- **Affordability** has no fixture, because the answer depends on the typed
  amount. The card asks for a backend instead of inventing a number.
- **Chat** returns the one pre-generated reply (`mocks/api_chat_response.json`).
- **Approving** returns "Running on fixtures, so nothing was written to Nessie."

Activity and profile are derived from `mocks/<persona>_snapshot.json`.

## How data flows

```
app/page.tsx (server component) ──► lib/api.ts ──┬─► TREASURER_API_BASE   (live)
                                                  └─► ../mocks/*.json      (fixtures)

components/* (browser) ──► /api/... (app/api/**/route.ts) ──► lib/api.ts ──► same switch
```

The page loads summary, forecast, bills, credit, alerts, activity and profile on
the server in one pass. Client components call the Next routes under `app/api/`,
which mirror the backend's paths exactly:

| Next route | Backend |
|---|---|
| `GET /api/users/[id]/{summary,forecast,bills,credit,alerts,activity,profile}` | same path |
| `POST /api/users/[id]/affordability` | same path |
| `POST /api/transfers/check` | same path |
| `POST /api/chat` | same path; copies only the `X-Model-*` headers across |
| `POST /api/actions/[id]/confirm` | same path |

After an approval the copilot calls `router.refresh()`, and the server component
re-reads everything, so the balance and runway visibly move.

In production, nginx sends `/api/` straight to FastAPI, so these routes are
bypassed there ([docs/deployment.md](../docs/deployment.md#what-production-actually-serves)).

## Your own model key

**Copilot → Use your own key.**
- Providers: Gemini (`AIza…`), Claude (`sk-ant-…`), or any OpenAI-compatible
  endpoint (`sk-…`, plus an optional base URL and model).
- Storage: `lib/model-key.ts` keeps the key in this browser's `localStorage`
  (`extreasurer.model-key`). Every access is guarded, because private windows
  throw.
- Transport: `app/api/chat/route.ts` forwards it as headers without reading or
  logging it. The backend spends it on one turn and keeps nothing.

The copilot shows who answered each reply. If the key does not work, it says
why, and the answer still arrives from the scripted router.
[docs/agent.md](../docs/agent.md#bring-your-own-key)

A key needs a live backend: in fixture mode there is nothing to spend it on, and
the panel says so.

## Rules this UI keeps

- **No number is computed here.** It formats money, dates and percentages, and
  converts currency with the API's `fx_rate`. Nothing else.
- Fixture mode is announced, simulated fields (`_simulated`) are labelled, and
  `executed_in_nessie: false` is shown as such.

## Layout

```
app/
  page.tsx              server component: loads everything, renders the dashboard
  layout.tsx            fonts, metadata
  globals.css           design system
  api/**/route.ts       proxies mirroring the backend contract
components/
  dashboard.tsx         shell, navigation, Overview/Runway/Bills/Credit/Safety views
  forecast-chart.tsx    the runway line
  affordability.tsx     "Can I afford it?"
  copilot.tsx           chat, approval cards, who-answered labels
  model-key.tsx         the key form
  safety.tsx            alerts, scenario runner, pause modal
  ui/button.tsx         shadcn button
lib/
  contract.ts           TypeScript types for every response (copied verbatim to mobile/lib)
  api.ts                the live/fixture switch
  format.ts             money, dates, percentages (copied verbatim to mobile/lib)
  model-key.ts          localStorage key store
  utils.ts              cn()
certificates/openssl.cnf  config for the local self-signed cert
```

## Checks

```bash
npx tsc --noEmit    # needed: next.config.mjs sets ignoreBuildErrors, so build will not catch type errors
```

`contract.ts` is also validated from Python: `tests/test_integration.py` parses
its required fields and asserts the API and `mocks/` provide them. If you change
it, copy it to `mobile/lib/contract.ts`; `cd ../mobile && npm run check` enforces
that the two stay identical.

`AGENTS.md` and `CLAUDE.md` here are written by `next dev` for coding agents.
Next 16 differs from older versions, so read `node_modules/next/dist/docs/`
before changing framework code.
