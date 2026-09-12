# EXTreasurer — mobile (P4)

The app from [begin.md §7](../begin.md) on a phone: overview with the runway
chart, bill decoder, credit builder, safety centre with the pre-transfer pause,
and the copilot — a tab of its own — with an approval gate in front of every
write. It will answer with your own model key if you give it one; see
[Your own model](#your-own-model).

Same product as [`../frontend`](../frontend/README.md), same backend, same
contract. What differs is the shape of the device, and one thing about how it
reaches the API — see [Switching to the real backend](#switching-to-the-real-backend).

## Run it

Node 20+ and Expo. npm, not pnpm: this app installs its dependencies nested
rather than hoisted, which is what Metro expects.

```bash
npm install
npm start       # then i (iOS), a (Android), w (web), or scan with Expo Go
```

`npm install` is not optional reading-material here: the key store needs
`expo-secure-store`, which is newer than the committed lockfile. If Metro says
it cannot resolve that module, it is the install that is missing:
`npx expo install expo-secure-store`.

No API key, no backend, no network needed. With `EXPO_PUBLIC_TREASURER_API_BASE`
unset the app reads P1's fixtures. If `../mocks` is missing, generate it:

```bash
cd .. && python -m seed.reset_demo
```

Personas: all three are in the header. `EXPO_PUBLIC_TREASURER_USER` picks who
launches first (`ana` is the demo).

## Switching to the real backend

```bash
cp .env.example .env
# EXPO_PUBLIC_TREASURER_API_BASE=http://127.0.0.1:8000
```

Three things about that line, each of which silently does nothing if you get it
wrong:

- **`EXPO_PUBLIC_` is not decoration.** Expo only inlines variables with that
  prefix into the bundle. This code runs on the phone, so an unprefixed name
  arrives as `undefined` and the app stays in mock mode without complaining.
- **`127.0.0.1` is the phone, not your laptop.** `lib/api.ts` rewrites a
  loopback host to the address Metro served the bundle from, so the line above
  works from a real device — as long as the phone and the laptop are on the same
  network and uvicorn is bound outward:

  ```bash
  cd .. && .venv/bin/uvicorn backend.api.app:app --host 0.0.0.0 --port 8000
  ```

- **CORS is the thing to get right, not a proxy.** The web app runs `lib/api.ts`
  on a server and puts its own `/api` routes in front of the browser. A phone has
  no server of its own, so these functions *are* the client and they call the
  backend directly. Both backends already send `access-control-allow-origin: *`
  — `backend/api/app.py` via `CORSMiddleware`, `backend/api/serve.py` by hand —
  so this works out of the box. It is only worth knowing about when it does not.

The header says which mode you are in, so nobody demos fixtures thinking they
are live.

## How the data gets in

```
app/(tabs)/*  ──►  lib/store.tsx  ──►  lib/api.ts  ──┬─► P3's FastAPI      (API_BASE set)
app/model-key    (one load, six tabs)                └─► bundled mocks/*.json (otherwise)
```

Two differences from the web app, both forced by the platform:

**No proxy layer.** There is no `app/api/**/route.ts` here, because there is no
server to host it. `lib/api.ts` is the whole data layer.

**One load, shared.** The web app is a single server-rendered page, so one
`Promise.all` at the top feeds every screen and `router.refresh()` re-runs it.
Tabs are not branches of one render, so that job moves to `lib/store.tsx`: fetch
once, share through context, and hand the copilot a `reload()` to call when an
action is approved. The currency toggle lives there for the same reason — a
toggle on the overview that the bills screen ignores is a bug.

The three shapes §7 does not define behave exactly as on the web:

| Needs | Mock mode | Live mode |
|---|---|---|
| Recent activity | derived from `<persona>_snapshot.json` | `GET /api/users/{id}/activity`, empty if absent |
| Home city, arrival date | `<persona>_snapshot.json` → `customer` | `GET /api/users/{id}/profile`, degrades if absent |
| "Can I afford $X?" | *nothing* — the card says so | `POST /api/users/{id}/affordability` |

The first two degrade instead of breaking. Affordability cannot: the answer
depends on the amount typed, so there is no fixture to pre-export and the card
asks for a backend rather than inventing a number.

## Your own model

The copilot's prose comes from whatever model the backend has a key for. That is
one key, on one laptop, belonging to one of us — so the phone can bring its own
instead: **Ask → the key button in the corner**, or the same screen at
`/model-key`.

Three providers, because the backend speaks three (`GET /api/health` →
`agent.byok.accepted` is the live list):

| | Key looks like | From |
|---|---|---|
| Google Gemini | `AIza…` | aistudio.google.com/apikey |
| Claude | `sk-ant-…` | console.anthropic.com/settings/keys |
| OpenAI-compatible | `sk-…` | platform.openai.com/api-keys, or any endpoint speaking that shape — OpenRouter, Groq, a model on the laptop |

Where it goes: `lib/secrets.ts` puts it in the phone's keystore — the iOS
keychain, Android's `EncryptedSharedPreferences` — not in AsyncStorage, which is
a plain file in the app sandbox. `lib/api.ts` sends it with each question as the
`X-Model-*` headers, and the backend spends it on that one turn and keeps
nothing: no disk, no log line (`backend/agent/keys.py`). On a device with no
keystore available the screen says so — the key then lasts until the app closes.

Two things worth knowing before demoing it:

- **A key needs the backend.** The tools that produce every number live there, so
  in fixture mode a stored key is stored for later, not used now. The copilot says
  this rather than letting a canned reply look like a conversation.
- **A key that does not work is reported, not swallowed.** A typo, an empty
  quota, a model name that does not exist: the answer still arrives — the backend's
  scripted router composes it from the same tools — and the copilot says the key
  did not write it, with the provider's own reason. Unreadable keys never leave
  the phone; `/model-key` applies the same rules the backend does.

## The fixtures are bundled, not read

The web app reads `mocks/` off disk at request time. A phone has no repository
to read, so Metro bundles the same files into the app — `metro.config.js` watches
`../mocks` so the requires in `lib/mocks.ts` resolve one directory up.

One set of fixtures, no second copy inside `mobile/` to drift away from the
first. The price is that every path in `lib/mocks.ts` is a literal: Metro
resolves `require` at build time, so a template string bundles nothing and fails
at runtime.

## Keeping the two apps saying the same thing

`lib/contract.ts` and `lib/format.ts` are copies of the web app's. Both apps
answer to the same backend and must describe it the same way, and a copy is only
safe if something notices when it stops being one:

```bash
npm run check          # contract:check + typecheck
```

`contract:check` compares both files against `../frontend/lib` byte for byte,
ignoring only the header comment above the first export. It fails loudly, because
the point of begin.md's shared contract is that drift shows up here rather than
on stage.

## What is honest about this UI

- **No number is computed here.** Balances, the runway date, the gap and every
  forecast point come from the engine through the API. This app formats and
  converts currency; that is all.
- **Fixture mode says so.** The header reads as fixtures until a backend is
  configured, and an approved action in fixture mode tells you nothing was
  written to Nessie.
- **Simulated fields are labelled**, because Nessie has no credit limit, APR or
  credit score.
- **A brought-along key is never re-used.** It is sent with the question it was
  meant for and forgotten by the server; nothing about it is written down
  anywhere but this phone.

## Demo path (begin.md §9)

Arm the demo data first, or the Safety tab is empty in live mode:

```bash
cd .. && python -m seed.reset_demo --arm
```

1. **Overview**, `$` ↔ `€` — the runway ends before the flight home.
2. **Runway** → the options, each with a measured effect → *Can I afford it?* →
   `47.34` → "Not yet", with the plan that turns it into a yes.
3. **Ask** → the same question in words → the proposed action card → Approve.
   Every other tab re-reads itself and the app walks you back to the overview:
   the balance and the runway date actually move.
4. **Safety** → *Send money* → the fake landlord transfer → the pause slides up
   over the thing you were about to do.
5. Same list, `Marta Aguirre` → goes through. That one matters: a check that
   stops everything is not a feature, and a judge will ask.

## Layout

```
app/
  _layout.tsx        fonts, the data store, the stack the tabs live in
  (tabs)/_layout.tsx the navy header and tab bar; six destinations
  (tabs)/index.tsx   overview
  (tabs)/runway.tsx  the projection, the fixes, affordability
  (tabs)/bills.tsx   the bill decoder
  (tabs)/credit.tsx  the credit builder
  (tabs)/safety.tsx  alerts and the pre-transfer pause
  (tabs)/copilot.tsx chat and the confirmation gate
  model-key.tsx      bring your own model key, as a modal route
components/
  ui.tsx             panels, eyebrows, buttons — the stylesheet's classes, as components
  forecast-chart.tsx the runway line, drawn from the forecast series
  affordability.tsx  "can I afford it?", answered by the engine
  fix-effect.tsx     what one fix buys, in the engine's own branch order
  safety.tsx         alerts, the scenario runner, the pause sheet
  persona-switch.tsx ana / raj / lucia, in the header
lib/
  contract.ts        every endpoint's response, as types   (copy of the web app's)
  format.ts          money, dates, percentages             (copy of the web app's)
  api.ts             mocks-or-backend, the one switch
  mocks.ts           the bundled fixtures
  secrets.ts         the model key, in the phone's keystore
  store.tsx          one load, six tabs, the currency toggle and the model key
  theme.ts           the design tokens, transcribed from globals.css
scripts/
  contract-check.mjs fails if the two contracts drift apart
```
