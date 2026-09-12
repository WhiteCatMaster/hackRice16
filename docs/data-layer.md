# The data layer (P1) — handoff

Written for P2, P3 and P4. What exists, what to call, and what the numbers mean.

## Run it

No dependencies. Python 3.11+, standard library only.

```bash
python -m seed.reset_demo        # generate + validate + load the cache + refresh mocks (~0.2s)
python -m backend.nessie.repo    # what is in the cache right now
python -m unittest discover tests
```

With a Nessie key in `.env`:

```bash
python -m seed.seed --push              # push everything to Nessie, then cache it
python -m backend.nessie.sync --source nessie --watch 30   # poll for new transactions
python -m seed.reset_demo --push        # wipe Nessie and start over
```

**Every read in the app goes through the cache, never straight to Nessie.** That is
what makes the demo survive a slow or dead API.

## What P2 calls

```python
from backend.nessie import db, repo

conn = db.connect()
snap = repo.snapshot(conn, "ana")     # everything about one persona in one call
```

`snapshot()` gives you `accounts`, `bills`, `deposits`, `withdrawals`, `transfers`,
`purchases` (joined to merchant name, category, lat/lng), `daily_spend_30d`,
`category_spend_30d` and `credit`. Also useful:

| Call | For |
|---|---|
| `repo.daily_spend(conn, account_id, days=30)` | burn rate, zero-filled so the median is honest |
| `repo.known_payee(conn, account_id, payee_account_id)` | "has she ever paid this payee?" |
| `repo.known_merchant(conn, account_id, merchant_id)` | "has she ever used this merchant?" |
| `repo.expected_forecast(conn, "ana")` | the numbers your forecast should reproduce |
| `repo.scenarios(conn, "ana")` | the scam/anomaly cases and what each should do |

### Test your engine against `expected_forecast`

The dataset is calibrated by running the forecast spec from `begin.md` §6 backwards.
So your forecast should land on the same numbers:

```python
expected = repo.expected_forecast(conn, "ana")
# runway_date 2026-10-10, gap 409.99, daily_discretionary 13.76, safety_buffer 100
```

If your engine disagrees with these, one of us has a bug — and finding that at hour
6 rather than hour 20 is the entire point of publishing them. `mocks/calibration.json`
has the same thing, plus `future_events`: every scheduled bill and expected deposit
between now and the flight home.

## What P3 and P4 call

`mocks/api_*.json` are shaped exactly like the endpoint contract in `begin.md` §7,
one file per endpoint per persona. Drop them in as fixtures.

Files whose top-level key says `"_owner": "P2 ..."` or `"_owner": "P3 ..."` fix the
*shape* only; the scores and replies in them are illustrative. Anything marked
`"_simulated"` is a field Nessie does not have — say so in the pitch.

## The demo numbers, and why they are what they are

Ana's data is not random. Two knobs (starting balance, daily discretionary spend)
are solved numerically until the forecast lands on the story:

| | |
|---|---|
| Checking | $1,735.06 |
| Savings | $2,600.00 |
| Card | $312.40 of a $500 limit → **62.5% utilization**, high enough to trigger the credit tip |
| Runs out | **2026-10-10** |
| Flies home | **2026-10-31** |
| Gap | **$409.99** |

That gap is deliberate: **a single $300 transfer does not close it.** The demo needs
both fixes — move $300 from savings *and* cap dining — which is why the action card
in the demo script has two lines. `tests/test_data_layer.py` asserts both halves.

Everything is relative to `DEMO_AS_OF` (default: today), so these dates move with the
calendar and the story stays true. `test_works_on_any_anchor_date` checks four
anchors.

Raj and Lucía are pinned rather than solved: Raj's stipend covers his outflow so
there is no shortfall to solve for, and Lucía is the healthy contrast. Both are there
to show the forecast is not hard-coded to one shape.

## Scenarios

Scam and anomaly cases are **not** in the seeded history, on purpose. "You have never
paid this payee" and "you have never used this merchant" are only true because of
that. Fire them when the demo needs them:

```bash
python -m seed.scenarios --list
python -m seed.scenarios fake_landlord          # into the cache
python -m seed.scenarios card_testing --push    # and into Nessie
python -m seed.scenarios --clear                # undo
```

| Key | Should |
|---|---|
| `fake_landlord` | PAUSE — $800 to a brand-new payee, urgent wording |
| `immigration_fine` | PAUSE — $1,200 round, agency impersonation |
| `legit_roommate` | **ALLOW** — a payee she has paid 3 times. The false-positive check |
| `card_testing` | ALERT — five sub-$3 charges at new merchants in 24 minutes, then $899 |
| `impossible_travel` | ALERT — Omaha then Miami, 2,253 km in 95 minutes |

`legit_roommate` matters as much as the other four: a risk engine that pauses
everything is not a feature, and a judge will ask.

A transfer scenario is staged as **pending**, never executed — the demo is about
stopping it before the money leaves.

## Before going on stage

```bash
python -m seed.reset_demo && python -m seed.scenarios --clear
```

Run it before every rehearsal too, so the runway chart looks identical every time.

## Layout

```
seed/
  personas.json       who the personas are and what the demo needs to be true
  merchants.json      Omaha-area places with real coordinates
  generator.py        builds the dataset; calibrate() solves the demo numbers
  validate.py         20 consistency checks; seed and reset refuse to run if any fail
  seed.py             push to Nessie, chronological, resumable
  scenarios.py        fire/clear scam and anomaly cases
  export_mocks.py     write mocks/
  reset_demo.py       one command back to the starting state
backend/nessie/
  config.py           .env, paths, DEMO_AS_OF
  client.py           REST client: retries, real error bodies
  db.py               SQLite schema, Nessie mirror + our own fields
  sync.py             load_local() and sync_from_nessie()
  repo.py             the read API P2 and P3 call
  timestamps.py       the day-precision workaround
tests/
  fake_nessie.py      in-memory API double
  test_data_layer.py  18 tests, including a full push/sync round trip
```
