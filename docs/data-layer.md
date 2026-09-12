# Data layer

`backend/nessie/` and `seed/`. Standard library only: `urllib`, `sqlite3`,
`json`. Nothing here can be broken by a failed `pip install`.

```
seed/personas.json ─┐
seed/merchants.json ┴─► seed/generator.py build(as_of) ─► seed/validate.py
                                   │
                  ┌────────────────┼────────────────────────┐
                  ▼                ▼                        ▼
      sync.load_local()     seed.seed --push          export_mocks.py
      (default, offline)    → Nessie → sync           → mocks/*.json
                  │                │
                  └──────► data/treasurer.db ◄── repo.py ◄── engine, API, agent
```

**Every read in the app goes through the cache.** Nessie is a place we write
to, not a place we read from at request time.

## Personas

| Key | Who | Language | Home currency | Flies home | Purpose |
|---|---|---|---|---|---|
| `ana` | Ana Etxeberria, exchange student from Bilbao in Omaha | es | EUR (0.92) | end of next month | **The demo.** Runs out of money before the flight |
| `raj` | Raj Krishnan, from Chennai | en | INR | end of the month after next | Regular stipend income; no shortfall |
| `lucia` | Lucia Moreno, from Monterrey | es | MXN | end of the month after next | Careful spender; the healthy contrast |

Each persona has a checking account, a savings account and a student credit
card. Ana's history covers 92 days: an arrival lump sum from home, monthly rent,
phone, insurance and gym. There is a streaming free trial about to convert, card
purchases around Omaha at real coordinates, and a roommate she has paid three
times. Supporting customers (a landlord, a roommate, scam payees) come from
`counterparties` in `personas.json`.

## Calibration: why Ana's numbers are what they are

Ana's data is not random. `generator.calibrate()` solves two knobs by bisection,
her starting checking balance and her daily discretionary spend. It solves until
the forecast tells the demo story: money runs out three weeks before the flight,
and the gap is about $410.

At `DEMO_AS_OF=2026-09-12`:

| | |
|---|---|
| Checking | $1,552.93 (solved) |
| Savings | $2,600.00 |
| Credit card | $312.40 of a $500 limit, 62.5% utilization, enough to trigger the credit tip |
| Daily discretionary spend | $10.65 (median of the last 30 days, measured from transactions) |
| Safety buffer | $100 |
| Runway date | **2026-10-10** |
| Flight home | **2026-10-31** |
| Gap | **$409.91** |

Things worth knowing:

- **Dates move with the calendar.** Everything is relative to `DEMO_AS_OF`
  (default today). The solver holds the runway-to-flight distance and the gap
  fixed, and moves the starting balance to get there. So the checking figure
  changes slightly day to day. Check `as_of` in the payload before suspecting a
  bug. `test_works_on_any_anchor_date` covers four anchors.
- **The published burn rate is measured, not solved.** Purchase amounts are
  rounded, so the median actually achievable differs from the solved knob by a
  fraction of a cent. The calibration publishes the measured figure, because
  that is all an engine reading transactions can see.
- **The balance lands mid-day, not on the edge.** It crosses the buffer in the
  middle of the runway day. Aiming one cent under made the date flip by a day on
  estimator noise.
- **One transfer is deliberately not enough.** The story needs a savings
  transfer *and* a spending cap. The engine's live plan is "Cap dining at $12 a
  week" plus "Move $400 from savings".
- The engine currently computes a gap of $425.90, not $409.91; see
  [engine.md](engine.md#known-discrepancy-with-the-calibration).

Raj and Lucia are pinned rather than solved; neither has a shortfall.

## Scenarios

Scam and anomaly cases are **not** in the seeded history. "You have never paid
this payee" is only true because of that. They are injected on demand.

| Key | Kind | Expected | What it is |
|---|---|---|---|
| `fake_landlord` | transfer | **pause** | $800 to a brand-new payee, "URGENT apartment deposit - pay today or you lose the place" |
| `immigration_fine` | transfer | **pause** | $1,200 round amount, agency impersonation, threat wording |
| `legit_roommate` | transfer | **allow** | A known payee, the usual amount. The false-positive control: it must not pause |
| `card_testing` | purchases | **alert** | Five sub-$3 charges at never-used merchants within 24 minutes, then $899 at Best Buy (above the card limit) |
| `impossible_travel` | purchases | **alert** | Omaha, then Miami 95 minutes later, about 2,250 km apart |

Transfer scenarios are staged as `pending`, never executed. Injected rows carry
`scenario` and `label` columns, which is how `--clear` finds them.

## Commands

All run from the repository root with the venv's Python.

| Command | Does |
|---|---|
| `python -m seed.reset_demo` | Generate, validate, wipe and reload the cache, refresh `mocks/`. About a second. Does not touch Nessie |
| `python -m seed.reset_demo --arm` | The same, then fire every scenario. **The state to demo and test from** |
| `python -m seed.reset_demo --scenario KEY` | Reset, then fire one scenario (repeatable) |
| `python -m seed.reset_demo --push` | Also delete previously seeded accounts from Nessie, push a fresh copy, pull it back. Add `--keep-nessie` to skip the delete |
| `python -m seed.reset_demo --as-of 2026-09-11 --no-mocks` | Override the anchor; skip rewriting fixtures |
| `python -m seed.scenarios --list` | List scenarios and expected outcomes |
| `python -m seed.scenarios KEY` / `all` | Inject into the cache; add `--push` to also write to Nessie |
| `python -m seed.scenarios --clear` | Remove every injected scenario row |
| `python -m seed.seed` | Generate, validate, load the cache (no network) |
| `python -m seed.seed --push [--resume] [--limit-purchases N]` | Push to Nessie in chronological order, then reconcile balances. `--resume` skips ids already in `id_map` |
| `python -m seed.export_mocks` | Rewrite the data fixtures in `mocks/` |
| `python -m seed.export_chat_fixture` | Rewrite `mocks/api_chat_response.json` from the live agent |
| `python -m seed.probe_nessie` | Test assumptions about the Nessie API with throwaway objects; writes `docs/probe-results.json` |
| `python -m backend.nessie.repo` | Print what is in the cache |
| `python -m backend.nessie.sync [--source nessie] [--watch SECONDS]` | Fill the cache locally (default) or by polling Nessie. **Do not use `--source nessie` before a demo** ([why](nessie-api-notes.md#balances-are-not-ours)) |

`validate.py` runs a set of consistency checks, for example that every stated
balance is reproducible from its transactions. Both `seed` and `reset_demo`
refuse to continue if any check fails.

## The cache

`data/treasurer.db`, created by `db.init()`. It is gitignored.

| Table | Holds |
|---|---|
| `customers` | Personas and counterparties, plus our fields: `persona_key`, `language`, `home_city`, `home_currency`, `fx_rate`, arrival and flight dates |
| `accounts` | Balances, plus `credit_limit`, `apr`, `statement_day`, `is_frozen`, `frozen_reason` |
| `merchants` | Name, category, geocode, `risk_tag` |
| `purchases`, `deposits`, `withdrawals`, `transfers`, `bills` | Nessie's objects, plus `occurred_at` timestamps, `label`, `scenario`, and `payee_id` on transfers |
| `payees` | Known-payee history, rebuilt from transfers by `db.rebuild_payees()` |
| `id_map` | Local id → Nessie id for everything pushed. **Survives `db.wipe()`**: it is the only record of what exists upstream |
| `sync_runs` | Log of loads and syncs |
| `meta` | Key/value: `calibration`, `scenarios`, `spending_caps`, `scenario_*_fired_at`, `last_nessie_sync` |

## Reading it from Python

```python
from backend.nessie import db, repo

conn = db.connect()
snap = repo.snapshot(conn, "ana")
```

`snapshot()` returns the customer, accounts, `as_of`, flight date, currency,
and the checking account's bills, deposits, withdrawals, transfers and purchases
(joined to merchant name, category and coordinates). It also has
`daily_spend_30d`, `category_spend_30d`, and a `credit` block with the simulated
fields listed.

| Function | Returns |
|---|---|
| `repo.resolve_customer(conn, "ana")` | The customer row, by persona key or id |
| `repo.account_of_type(conn, customer_id, "Savings")` | One account |
| `repo.daily_spend(conn, account_id, days=30)` | Spend per day, zero-filled so a median is honest |
| `repo.category_spend(conn, account_id, days=30)` | Spend per category |
| `repo.known_payee(conn, account_id, payee_account_id)` | Prior payments to that payee, or `None` |
| `repo.known_merchant(conn, account_id, merchant_id)` | Prior purchases there, or `None` |
| `repo.expected_forecast(conn, "ana")` | The calibration numbers an engine should reproduce |
| `repo.scenarios(conn, persona_key=None)` | Scenario definitions |
| `repo.as_of(conn)` | The demo's "today" |

## Fixtures in `mocks/`

Both apps render these when no backend is configured. They are shaped exactly
like the API responses.

| File | Written by |
|---|---|
| `dataset.json`, `<persona>_snapshot.json`, `calibration.json`, `scenarios.json`, `index.json` | `seed.export_mocks` (also run by `reset_demo`) |
| `api_users_<persona>_{summary,forecast,bills,credit}.json` | `seed.export_mocks`, from the calibration's reference projection |
| `api_users_<persona>_alerts.json`, `api_transfers_check_{fake_landlord,immigration_fine,legit_roommate}.json` | `python -m backend.engine.export`, with every scenario fired |
| `engine_check.json` | `python -m backend.engine.export`: the engine compared with the calibration |
| `api_chat_response.json` | `seed.export_chat_fixture`: the agent's real answer to the §9 question |

Keys starting with `_` (`_source`, `_owner`, `_note`, `_simulated`) are
metadata, not data.
