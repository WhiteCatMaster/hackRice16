# exchange-treasurer

A new Expo app, created from `create-expo-app`'s default template on 2026-09-12
(commit `76c288c`). **It contains only the template so far.** It does not
use the API, the fixtures, or any code from `mobile/`. The working phone app is
still [`../mobile`](../mobile/README.md).

| | |
|---|---|
| Expo SDK | 57 (`expo ~57.0.22`), React Native 0.86.3, React 19.2.3 |
| Routing | Expo Router, typed routes, source under `src/app/` |
| Enabled | React Compiler (`experiments.reactCompiler`), `@expo/ui`, Reanimated 4, glass effect, symbols |
| Identifiers | name and slug `exchange-treasurer`, scheme `exchangetreasurer` (`app.json`) |

## Run

```bash
npm install
npm start          # or: npm run ios | android | web
npm run lint
```

`npm run reset-project` moves the template screens to `app-example/` and leaves
a blank app. That is the usual first step before building real screens.

## Structure

```
src/app/            _layout.tsx, index.tsx, explore.tsx   (template screens)
src/components/     themed text/view, tabs, collapsible, animated icon
src/constants/theme.ts
src/hooks/          color scheme, theme
assets/             template icons and images
scripts/reset-project.js
```

## If you build on this

- Expo 57 changed a lot; `AGENTS.md` asks coding agents to read the versioned
  docs at https://docs.expo.dev/versions/v57.0.0/ first.
- The backend contract is `frontend/lib/contract.ts`. `mobile/` shows how to
  consume it on a phone: bundled fixtures, the loopback rewrite, a secure key
  store ([mobile/README.md](../mobile/README.md)).
- Use npm, as `mobile/` does.
