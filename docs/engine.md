# Engine

`backend/engine/`. It turns the cache into answers: when the money runs out,
what would fix it, whether a purchase is affordable, whether a transfer looks
like a scam. Its functions take a SQLite connection and a persona, and return
dictionaries already shaped like the API contract. There is no model and no
network, and the same input always gives the same output.

## Status: bytecode only

**There is no `.py` source for the engine in git, on any branch.** What
survived was the compiled output. The ten modules are committed as sourceless
`.pyc` files where their source should be, and Python imports those directly:

```
backend/engine/__init__.pyc   __main__.pyc   advice.pyc     evaluate.pyc   export.pyc
               forecast.pyc   projection.pyc recurring.pyc  risk.pyc       service.pyc
```

What follows from that:

- **It cannot be edited.** Whoever still has the source should commit it.
- **It runs only on Python 3.13.** The files carry the 3.13 magic number. On any
  other interpreter the import fails. `backend/api/engine_port.py` then falls
  back to `backend/api/reference.py` for every capability, logs one warning,
  and keeps serving. Nothing crashes, which is exactly why it is easy to miss.
- **`*.pyc` is in `.gitignore`.** These files are tracked only because they
  were force-added (`git add -f`). The copies under `backend/engine/__pycache__/`
  are local build output.

Before any demo, check who is answering:

```bash
curl -s localhost:8000/api/health | python3 -m json.tool   # engine.engine_module must be "backend.engine"
```

Every payload also says it: `"_engine": "backend.engine"` or `"p3-reference"`.

## Capabilities

`engine_port.CAPABILITIES` lists the twelve names the API resolves. Each one is
resolved per call, so a fixed import takes over without a restart.

| Capability | Called by | Returns |
|---|---|---|
| `summary(conn, user)` | `GET …/summary`, `get_summary` tool | Balances, `runway_date`, `target_date`, `gap`, `daily_burn`, `days_of_runway`, `open_alerts`, currency and FX |
| `forecast(conn, user, target=None)` | `GET …/forecast`, `get_forecast` tool, the confirmation gate | Daily `series`, scheduled `events`, `min_balance`, `burn_profile`, `fixes`, `also_detected` |
| `bills(conn, user)` | `GET …/bills` | Each bill with `next_date`, `days_away`, a plain-language `explanation`, `covered`, `heads_up` for trials |
| `credit(conn, user)` | `GET …/credit` | Balance, simulated limit and utilization, `suggested_payment`, `interest_if_carried`, `tip`, `explanations` |
| `affordability(conn, user, amount, when=None)` | `POST …/affordability`, `check_affordability` tool | `affordable`, `max_safe_amount`, `max_safe_through`, `already_short`, `if_you_fix_first`, a written `reason` |
| `can_afford` | Internal / older name | Simpler affordability |
| `suggest_fixes(conn, user)` | `GET …/fixes`, `suggest_fixes` tool | Candidate actions, each with a measured `effect`, `in_plan` and `effect_with_plan` |
| `check_transfer(conn, user, payee_id, amount, description, payee_name)` | `POST /api/transfers/check`, `check_transfer` tool | `risk_score`, `pause`, `verdict`, `reasons`, `questions`, scored `signals`, `runway_date_after` |
| `alerts(conn, user)` | `GET …/alerts` | Open scam and anomaly alerts |
| `detect_anomalies(conn, user)` | `alerts` | Card-testing bursts and impossible travel in purchases |
| `activity(conn, user, limit)` | `GET …/activity` | Recent movements, signed, newest first |
| `profile(conn, user)` | `GET …/profile` | Name, home city, address city/state, language, arrival, flight home, currency |

The module also exports `check_scenario`, `combine_fixes`, `recommended_plan`,
and the submodules `advice`, `projection`, `recurring`, `risk`, `service`.

## How the forecast works

These are observable from its output (`forecast()["burn_profile"]` names its
own method).

1. **Start** from the current checking balance. Savings are shown as a reserve,
   not spent.
2. **Scheduled events.** Recurring bills on their due dates and expected
   deposits, between today and the target date (default: the flight home).
3. **Variable spending.** The median of the last 30 days of daily spend,
   zero-filled so days without spending count. It also reports weekday and
   weekend medians, the mean, and spend per category.
4. **Step day by day** to the target.
5. **Runway date:** the first day the balance drops below the $100 safety
   buffer, or `null` if it never does. A `null` runway is good news, not
   missing data.
6. **Gap:** how much more money would keep the balance at the buffer through
   the target date.

For Ana on 2026-09-12: start $1,552.93, burn $10.65/day, runway 2026-10-10, low
point −$325.90 on 2026-10-31, gap $425.90.

## Fixes and the plan

`suggest_fixes()` proposes concrete actions: a category cap, cancelling a trial
before it converts, a transfer from savings. It re-runs the projection for each
one and attaches:

- `effect`: that fix alone (`runway_date_after`, `gap_after`, `days_gained`,
  `clears_the_gap`).
- `in_plan`: whether it belongs to the recommended combination.
- `effect_with_plan`: the combined plan (for Ana, a dining cap at $12/week plus
  $400 from savings takes `gap_after` to 0 and gains 21 days).

The agent and the approval cards quote these measured effects, not what a fix
advertises.

## Scam check

`check_transfer()` scores a transfer before it happens, from the user's own
history, and returns every signal with its points. For `fake_landlord`:

| Signal | Points | Reason shown |
|---|---|---|
| `new_payee` | 30 | You have never sent money to this payee |
| `large_share` | 18 | This is 52% of your checking balance |
| `urgency` | 15 | The message uses urgent or threatening language (matched `URGENT`) |
| `breaks_runway` | 8 | It brings the day your money runs out forward by 9 days |
| `round_amount` | 7 | Round amount |
| `large_amount` | 6 | $800 is a large single payment |

The total is score 84 and `pause: true`, with three questions to ask. The
`legit_roommate` control (known payee, usual amount) scores 0 and is allowed.
The app pauses; the user decides.

`detect_anomalies()` looks for card-testing bursts (several tiny charges at
new merchants, then a large one) and impossible travel (purchases too far apart
for the time between them, using our own timestamps).

## Evaluation

```bash
python -m backend.engine.evaluate    # writes docs/engine-evaluation.json
```

| Metric | Result |
|---|---|
| Scenario outcomes | 5 / 5 correct (2 pause, 1 allow, 2 alert) |
| Injected fraud purchases flagged | 8 / 8 |
| Normal purchases flagged | 0 / 480 |

This is synthetic data that we generated and labelled ourselves. It shows the
rules fire on the designed attacks and stay quiet on normal history. It is not
evidence about real-world fraud; say so if asked.

## Command-line tools

```bash
python -m backend.engine             # Ana's forecast, fixes and scam checks, printed
python -m backend.engine raj         # another persona
python -m backend.engine.evaluate    # the evaluation above
python -m backend.engine.export      # rewrites 6 fixtures in mocks/ + mocks/engine_check.json
```

`export` writes `api_users_*_alerts.json` and `api_transfers_check_*.json` with
every scenario fired. It also compares the engine with the calibration within
tolerances (gap $1, min balance $1, burn $0.05, runway 1 day). Run it only when
you mean to change the committed fixtures.

## Known discrepancy with the calibration

On 2026-09-12 the engine and the calibration agree on Ana's runway date
(2026-10-10) and burn rate ($10.65). They **disagree on the gap: $425.90 against
$409.91.** The $15.99 difference is the size of the streaming bill that the
engine schedules and the calibration's future events do not. Raj and Lucia
agree exactly.

Consequences:

- Fixture mode shows a gap of $409.91; live mode shows $425.90.
- `mocks/engine_check.json` in git says `"exact": true`. It predates the
  current state. Running `python -m backend.engine.export` would regenerate it
  and report the difference.

Settle this before a demo by deciding which side is right. You cannot fix it in
the engine without its source.

## The fallback: `backend/api/reference.py`

A stand-in, written so the API could answer before the engine existed. It
reproduces the calibration's published projection, pinned field by field in
`tests/test_api.py::TestReferenceMatchesCalibration`. It uses the generator's
calibrated burn rate, so it is a check on the data rather than an independent
forecast.

What it does **not** return: `already_short` and `max_safe_through` on
affordability, and `days_gained` on a fix's effect. Screens that use those fall
back to less precise wording, and five tests in `tests/test_integration.py`
fail. Those five failing together is the signature of "engine not loaded".

It has one hook the confirmation gate relies on:

```python
forecast(conn, user, target=None, extra_events=[{"date": "2026-09-12", "amount": 400.0, "label": "Transfer"}])
```

Signed amounts are merged into the projection like any scheduled event. The gate
calls `engine_port.accepts("forecast", "extra_events")`. If the live forecast
does not take the hook, the gate measures both *before* and *after* with the
reference and labels the effect `measured_by: "p3-reference"`, so an approval
card never mixes two engines.

### Lesson from a one-day disagreement

The reference and the engine once disagreed on Ana's runway by one day. The
cause was first misdiagnosed as rounding drift in the projection. The real cause
was the input: the engine measured the burn rate from transactions, the
generator projected from its solved knob, and the two differed in the fourth
decimal place. The data was retuned so they agree. When chasing the next
off-by-one, vary one input at a time against a fixed projection before blaming
the projection. The reference rounds only on output, and
`test_rounding_does_not_drift` holds it to that.
