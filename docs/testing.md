# Testing

## Python: 141 tests

```bash
.venv/bin/python -m unittest discover tests            # everything, about 15 seconds
.venv/bin/python -m unittest tests.test_api -v         # one file
.venv/bin/python -m unittest tests.test_api.TestBringYourOwnKey
```

Last run on 2026-09-12, Python 3.13.15: **141 passed**.

The suites build their own temporary SQLite caches from the generator, so they
do not depend on, or modify, `data/treasurer.db`. They never write to Nessie:
the confirmation-gate tests pin `NESSIE_API_KEY` empty, and the Nessie round
trip uses `tests/fake_nessie.py`, an in-memory double.

One exception to "no network": **if the root `.env` holds a model key**, a couple
of agent tests make real model calls. When Gemini's free quota is spent, you will
see `gemini turn failed (HTTP 429 …); falling back to the scripted router` in the
output. The tests still pass, since fallback is the behaviour under test. Unset
the key in your shell to keep the run offline.

### `tests/test_data_layer.py`: 25 tests

| Class | Covers |
|---|---|
| `TestGenerator` | Determinism, calibration targets, the two-fix story, four anchor dates |
| `TestCache` | Loading, `repo` reads, zero-filled daily spend, known payees |
| `TestNessieRoundTrip` | Full push and sync against `FakeNessie`, id mapping, restored local-only fields |
| `TestAccessChecks` | `check_access()` distinguishing unreachable / no key / bad key / ok |
| `TestRunwayRobustness` | The runway date survives small estimator error |

### `tests/test_api.py`: 90 tests

| Class | Covers |
|---|---|
| `TestReferenceMatchesCalibration` | The fallback reproduces the calibration field by field |
| `TestDemoInvariants` | What the demo depends on, for whichever engine is live |
| `TestContractShapes` | Response fields per endpoint |
| `TestRisk` | Scam scenarios pause, the roommate is allowed |
| `TestConfirmationGate` | Propose never moves money, confirm does once, measured effects, restart recovery |
| `TestAgent` | Scripted answers, language detection, the backstop proposal, `test_the_agent_cannot_move_money` |
| `TestEnginePort` | Per-capability resolution, dropped kwargs, `accepts()` |
| `TestHandlers` | Status codes and error bodies |
| `TestChatFixture` | `mocks/api_chat_response.json` agrees with the live agent |
| `TestHttpRoutes` | The stdlib server over real HTTP, including `test_the_full_demo_path` (dashboard → Spanish chat → approve → runway moves → landlord paused → roommate allowed) |
| `TestModelKey` | Header parsing and validation rules |
| `TestBringYourOwnKey` | Key precedence, rejection metadata, nothing persisted |
| `TestOpenAICompatibleTurn` | A full tool-calling turn against a local fake OpenAI server |

### `tests/test_integration.py`: 26 tests

The seam between the backend and the frontend, tested from both sides.

| Class | Asserts |
|---|---|
| `TestContractIsSatisfied` | The API returns every field `frontend/lib/contract.ts` marks required, and `mocks/` does too. Fields are read by parsing the TypeScript |
| `TestConfirmationGate` | Approving through handlers changes the numbers the screens re-read |
| `TestMocksMatchLive` | An armed cache shows the same alerts the fixtures ship |
| `TestCleanCacheIsCalm` | An unarmed cache has no alerts, and that is not an error |
| `TestNullRunwayIsGoodNews` | `runway_date: null` flows through as "lasts past the flight" |
| `TestFrontendWiring` | Every endpoint `frontend/lib/api.ts` calls exists in the backend and has a Next route |

If exactly five integration tests fail together, the engine did not import
(wrong Python). They need `already_short`, `max_safe_through` and `days_gained`,
which only the real engine returns. See [engine.md](engine.md#the-fallback-backendapireferencepy).

## Cross-layer checks outside the suite

| Command | Checks |
|---|---|
| `cd mobile && npm run check` | `lib/contract.ts` and `lib/format.ts` match `frontend/lib/` byte for byte, ignoring the header comment; then `tsc --noEmit` |
| `python -m backend.engine.export` | Engine versus calibration within tolerance. **Rewrites six fixtures**, so commit only on purpose |
| `python -m backend.engine.evaluate` | Scenario outcomes and detection/false-positive rates, into `docs/engine-evaluation.json` |
| `python -m seed.export_chat_fixture` | Regenerates the chat fixture from the live agent |
| `curl -s localhost:8000/api/health` | Engine module, agent mode, cache counts |

## Frontends

- **Web** has no test runner. `next.config.mjs` sets
  `typescript.ignoreBuildErrors: true`, so `pnpm build` will not catch type
  errors. Run `cd frontend && npx tsc --noEmit`.
- **Phone** has Jest configured (`jest-expo/ios` preset, `jest.setup.tsx`,
  `@testing-library/react-native`) but no test files and no `test` script yet.
  Run `npx jest` once tests exist.

## Before committing

```bash
.venv/bin/python -m unittest discover tests
(cd mobile && npm run check)
(cd frontend && npx tsc --noEmit)
```

If you changed data, engine output or the router, also regenerate the chat
fixture.
