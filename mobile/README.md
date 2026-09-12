# EXTreasurer phone app

Expo SDK 57, React Native 0.86, Expo Router. It is the same product as the
[web app](../frontend/README.md) against the same API, in six tabs:

- **Overview**
- **Runway**: projection, fixes, affordability
- **Bills**
- **Credit**
- **Safety**: alerts, *Send money*, the pause sheet
- **Ask**: the copilot

`/model-key` is a modal for the user's own model key. The persona switch
(ana / raj / lucia) is in the header.

## Run

Node 20+ and **npm**. Do not use pnpm: Metro expects this app's dependencies
installed nested, not hoisted.

```bash
npm install
npm start           # i: iOS simulator · a: Android · w: web · or scan the QR with Expo Go
npm run ios | android | web
```

## Two modes, one variable

```bash
cp .env.example .env
# EXPO_PUBLIC_TREASURER_API_BASE=http://127.0.0.1:8000
```

| `EXPO_PUBLIC_TREASURER_API_BASE` | Data comes from | Header reads |
|---|---|---|
| unset | Fixtures from `../mocks`, **bundled into the app** by Metro | FIXTURES · AS OF … |
| set | The API, called directly from the phone | LIVE BACKEND · NESSIE-BACKED |

`EXPO_PUBLIC_TREASURER_USER` picks the launch persona. Restart Metro
(`npm start -- --clear`) after changing `.env`.

Three things that fail silently if wrong:

1. **The `EXPO_PUBLIC_` prefix.** Expo only inlines prefixed variables; without
   it the value is `undefined` and the app stays on fixtures.
2. **`127.0.0.1` means the phone.** On native, `lib/api.ts` rewrites a loopback
   host to the LAN address Metro served the bundle from, keeping the port. The
   API must listen on that address, and the phone must be on the same network:
   ```bash
   cd .. && .venv/bin/uvicorn backend.api.app:app --host 0.0.0.0 --port 8000
   ```
3. **CORS, not a proxy.** There is no server in a phone app, so there are no
   proxy routes; `lib/api.ts` is the client. Both backends already allow any
   origin and the `X-Model-*` headers.

Requests time out after 10 seconds and render as empty, not as a spinner that
never ends.

## How data flows

```
app/(tabs)/*  ──►  lib/store.tsx  ──►  lib/api.ts  ──┬─► API                (live)
app/model-key     one load, shared                  └─► lib/mocks.ts       (bundled fixtures)
```

`lib/store.tsx` loads summary, forecast, bills, credit, alerts, activity and
profile once per persona and shares them through context. It also holds the
currency toggle, so every tab converts together, and the model key. The copilot
calls `reload()` after an approval; every tab re-reads, and the app returns to
Overview.

**Fixtures are bundled, not read.** `metro.config.js` adds `../mocks` to
`watchFolders`, and `lib/mocks.ts` `require`s each file by literal path. Metro
resolves requires at build time, so a template-string path would bundle nothing.
Adding a persona or fixture means adding lines there.

Fixture mode has the same limits as the web: no affordability, one canned chat
reply, and approvals that say nothing was written.

## Your own model key

**Ask → the key button**, or navigate to `/model-key`. It supports the same
three providers as the web.

| Platform | Stored in (`lib/secrets.ts`) |
|---|---|
| iOS / Android | `expo-secure-store`: iOS Keychain, Android EncryptedSharedPreferences |
| Web | `localStorage` |
| Neither available | Memory for this session only; the screen says so |

It is never stored in AsyncStorage, which is a plain file. `lib/api.ts` sends
the key as `X-Model-*` headers with each question, and the backend keeps
nothing. Unreadable keys are rejected on the phone with the same rules the
backend applies. [docs/agent.md](../docs/agent.md#bring-your-own-key)

## Keeping in step with the web app

`lib/contract.ts` and `lib/format.ts` are copies of `frontend/lib/`. Only the
header comment above the first export may differ.

```bash
npm run check           # contract:check (byte comparison) + typecheck (tsc --noEmit)
npm run contract:check  # prints the first differing line and the cp command to fix it
npm run doctor          # expo-doctor
```

## Tests

Jest is configured (`jest.config.js`, preset `jest-expo/ios`; `jest.setup.tsx`;
`@testing-library/react-native`; an icon mock in `__mocks__/`). **There are no
test files yet, and no `test` script.** Put tests under `__tests__/` or next to
the code as `*.test.tsx`, and run `npx jest`.

## Layout

```
app/
  _layout.tsx           fonts (Fraunces, IBM Plex Sans/Mono), data store, root stack
  (tabs)/_layout.tsx    header with persona switch and live/fixture status; the tab bar
  (tabs)/index.tsx      Overview
  (tabs)/runway.tsx     projection, fixes, affordability
  (tabs)/bills.tsx      bill decoder
  (tabs)/credit.tsx     credit builder
  (tabs)/safety.tsx     alerts, Send money, pause sheet
  (tabs)/copilot.tsx    Ask: chat, approval cards, who answered
  model-key.tsx         the key form, as a modal
components/
  ui.tsx                panels, eyebrows, buttons
  forecast-chart.tsx    runway line (react-native-svg)
  affordability.tsx     "Can I afford it?"
  fix-effect.tsx        what one fix buys, following the engine's branch order
  safety.tsx            alerts, scenario runner, pause sheet
  persona-switch.tsx    ana / raj / lucia
lib/
  contract.ts           response types (copy of the web app's)
  format.ts             formatting (copy of the web app's)
  api.ts                live/fixture switch, loopback rewrite, timeout
  mocks.ts              bundled fixture map
  secrets.ts            model key storage
  store.tsx             shared data, currency toggle, key
  theme.ts              design tokens
scripts/contract-check.mjs
```

App identifiers (`app.json`): name `EXTreasurer`, slug `exchangetreasurer`,
scheme `treasurer`, bundle/package `com.exchangetreasurer.mobile`.
