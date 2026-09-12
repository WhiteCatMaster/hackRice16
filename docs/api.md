# API reference

Base URL: `http://localhost:8000` locally, `https://exchangetreasurer.us` in
production. JSON in and out; no authentication.

## Running it

```bash
.venv/bin/uvicorn backend.api.app:app --port 8000 --reload   # FastAPI; docs at /docs
.venv/bin/python -m backend.api.serve 8000                   # the same routes, standard library only
```

Both are thin wrappers over `backend/api/handlers.py`, whose functions return
`(status, dict)` and import no web framework. Both send CORS headers:
`app.py` allows everything, and `serve.py` allows any origin plus
`content-type` and the four `X-Model-*` headers. Browsers and phones can
therefore call the API directly.

## Conventions

- **Personas** are `ana`, `raj`, `lucia`. A customer id also resolves.
- **Money** is in US dollars as numbers; **dates** are `YYYY-MM-DD`; timestamps
  are `YYYY-MM-DDTHH:MM`.
- **Metadata keys start with `_`**:
  - `_engine`: who computed the payload, `backend.engine` or `p3-reference`.
  - `_simulated`: fields Nessie does not have.
  - `_note`: a human explanation.
- **Errors** are `{"error": code, "message": text}`:

| Status | `error` | When |
|---|---|---|
| 404 | `unknown_user` | Persona does not exist |
| 404 | `unknown_scenario` | `scenario` key on a transfer check does not exist |
| 400 | `bad_amount` | `amount` missing or not numeric |
| 400 | `empty_message` | Chat with no `message` |
| 400 | `bad_model_key` | A brought-along model key is unreadable ([agent.md](agent.md#bring-your-own-key)) |
| 400 | `bad_action` | Unsupported action type on propose |
| 400 | `bad_json` | Body is not JSON (stdlib server only; FastAPI treats it as `{}`) |
| 404 | `not_found` | Unknown route (stdlib server; FastAPI answers `{"detail": "Not Found"}`) |
| 500 | `handler_failed` | Uncaught exception (stdlib server) |

## Endpoints

| Method | Path | Summary |
|---|---|---|
| GET | [`/api/health`](#get-apihealth) | Who answers what; cache counts |
| GET | [`/api/users/{user}/summary`](#get-apiusersusersummary) | Balances, runway, gap |
| GET | [`/api/users/{user}/forecast`](#get-apiusersuserforecast) | Daily projection, events, fixes |
| GET | [`/api/users/{user}/bills`](#get-apiusersuserbills) | Bills explained |
| GET | [`/api/users/{user}/credit`](#get-apiusersusercredit) | Card utilization and advice |
| GET | [`/api/users/{user}/alerts`](#get-apiusersuseralerts) | Open scam and anomaly alerts |
| GET | [`/api/users/{user}/activity`](#get-apiusersuseractivity) | Recent movements |
| GET | [`/api/users/{user}/profile`](#get-apiusersuserprofile) | Who the persona is |
| GET | [`/api/users/{user}/fixes`](#get-apiusersuserfixes) | Candidate actions with measured effects |
| GET | [`/api/scenarios`](#get-apiscenarios) | Seeded scam and anomaly cases |
| POST | [`/api/users/{user}/affordability`](#post-apiusersuseraffordability) | Can they spend this? |
| POST | [`/api/transfers/check`](#post-apitransferscheck) | Risk-check a transfer before it happens |
| POST | [`/api/chat`](#post-apichat) | Ask the copilot |
| POST | [`/api/actions/propose`](#post-apiactionspropose) | Stage an action without chat |
| POST | [`/api/actions/{id}/confirm`](#post-apiactionsidconfirm) | Execute a staged action. The only write |

Examples below are real responses for Ana on 2026-09-12, trimmed.

### `GET /api/health`

`?probe=1` also checks Nessie. It GETs `/customers`, then POSTs an empty
customer: the key is validated before the body, so this reveals whether writes
would work while creating nothing. The probe is opt-in because it makes network
calls. A dead Nessie never makes health report `ok: false`.

```json
{
  "ok": true, "service": "exchangetreasurer-api", "as_of": "2026-09-12",
  "cache": {"customers": 6, "accounts": 12, "merchants": 30, "purchases": 480, "bills": 12,
            "deposits": 23, "withdrawals": 35, "transfers": 4, "payees": 2},
  "personas": ["ana", "lucia", "raj"],
  "nessie": {"base_url": "https://api.nessieisreal.com", "key_present": true, "probed": false},
  "agent": {
    "mode": "llm", "provider": "gemini", "model": "gemini-flash-latest",
    "anthropic_sdk": true, "api_key_present": true,
    "tools": ["get_summary", "get_forecast", "check_affordability", "…"],
    "byok": {"accepted": ["gemini", "anthropic", "openai"],
             "headers": {"provider": "x-model-provider", "key": "x-model-key",
                         "model": "x-model-name", "base_url": "x-model-base-url"}}
  },
  "engine": {
    "engine_module": "backend.engine",
    "capabilities": {"summary": "backend.engine", "forecast": "backend.engine", "…": "…"},
    "from_p2": ["activity", "affordability", "…"], "from_reference": []
  }
}
```

With probing: `nessie` gains `probed: true`, `reachable`, `authorized`, `detail`.

### `GET /api/users/{user}/summary`

```json
{
  "user": "ana", "name": "Ana Etxeberria", "as_of": "2026-09-12",
  "accounts": [
    {"id": "…", "type": "Checking", "nickname": "Ana Checking", "balance": 1552.93},
    {"id": "…", "type": "Credit Card", "nickname": "Ana Student Card", "balance": 312.4,
     "limit": 500.0, "utilization": 0.6248},
    {"id": "…", "type": "Savings", "nickname": "Ana Savings", "balance": 2600.0}
  ],
  "runway_date": "2026-10-10", "target_date": "2026-10-31", "gap": 425.9,
  "safety_buffer": 100.0, "daily_burn": 10.65, "days_of_runway": 28,
  "currency": "USD", "home_currency": "EUR", "fx_rate": 0.92, "language": "es",
  "open_alerts": 0,
  "_simulated": ["limit", "utilization", "fx_rate"], "_engine": "backend.engine"
}
```

`runway_date: null` means the money lasts past the target date.

### `GET /api/users/{user}/forecast`

Query: `target=YYYY-MM-DD` (default: flight home).

```json
{
  "user": "ana", "target": "2026-10-31",
  "runway_date": "2026-10-10", "gap": 425.9,
  "min_balance": -325.9, "min_balance_date": "2026-10-31",
  "daily_burn": 10.65, "safety_buffer": 100.0, "starting_balance": 1552.93,
  "series": [{"date": "2026-09-12", "balance": 1552.93, "events": []},
             {"date": "2026-09-13", "balance": 1542.28, "events": []}],
  "events": [{"date": "2026-09-15", "amount": -30.0, "label": "Gym", "kind": "bill"},
             {"date": "2026-09-20", "amount": -15.99, "label": "Streaming", "kind": "bill"}],
  "burn_profile": {"daily_burn": 10.65, "mean": 12.34, "weekday_median": 8.77,
                   "weekend_median": 12.39, "days_observed": 30,
                   "per_day_by_category": {"groceries": 5.94, "dining": 2.79},
                   "method": "median of the last 30 days, zero-filled"},
  "fixes": ["… same shape as /fixes …"],
  "applied": [], "also_detected": [], "_engine": "backend.engine"
}
```

### `GET /api/users/{user}/bills`

```json
{
  "user": "ana",
  "bills": [
    {"id": "…", "nickname": "Gym", "payee": "Planet Fitness", "amount": 30.0,
     "next_date": "2026-09-15", "days_away": 3, "recurring_day": 15, "cadence": "monthly",
     "category": "fitness", "covered": true, "usual_amount": 30.0, "times_paid": 3,
     "payments_left": 2,
     "explanation": "Gym membership. US gyms usually need written cancellation notice, so cancel before you fly home or it keeps charging."},
    {"nickname": "Streaming", "payee": "Spotify", "amount": 15.99, "next_date": "2026-09-20",
     "heads_up": "Free trial ends 2026-09-21, then 15.99/month", "…": "…"}
  ]
}
```

### `GET /api/users/{user}/credit`

```json
{
  "user": "ana", "account_id": "…", "balance": 312.4, "limit": 500.0, "utilization": 0.6248,
  "apr": 24.99, "statement_day": 22, "suggested_payment": 162.4, "available": 187.6,
  "interest_if_carried": 6.51,
  "tip": "You are using 62% of your limit. Paying it down below 30% (about $162.40) is what US credit scoring rewards.",
  "explanations": [{"title": "Current balance is not what you owe this month", "body": "…"}]
}
```

Limit, APR and utilization are simulated.

### `GET /api/users/{user}/alerts`

`{"user": "ana", "alerts": [ … ]}`. The list is empty until scenarios are fired
(`seed.reset_demo --arm`); armed, Ana has four. Each alert has a title such as
"Transfer paused", "Unusual card activity" or "Purchases too far apart", and
the reasons behind it.

### `GET /api/users/{user}/activity`

Query: `limit` (default 8).

```json
{"user": "ana", "items": [
  {"id": "…", "label": "Trader Joe's", "category": "groceries",
   "occurred_at": "2026-09-12T21:09", "amount": -29.73, "kind": "purchase"}
]}
```

`kind` is `purchase`, `deposit`, `withdrawal` or `transfer`. Money out is negative.

### `GET /api/users/{user}/profile`

```json
{"name": "Ana Etxeberria", "home_city": "Bilbao, Spain", "city": "Omaha", "state": "NE",
 "language": "es", "arrival_date": "2026-06-12", "flight_home_date": "2026-10-31",
 "home_currency": "EUR", "fx_rate": 0.92}
```

### `GET /api/users/{user}/fixes`

```json
{"user": "ana", "fixes": [
  {"id": "cap_dining", "type": "category_cap", "label": "Cap dining at $12 a week",
   "amount": 54.69,
   "detail": "You spend about $2.79 a day on dining. Cutting that by 40% saves $1.12 a day until you fly home.",
   "effect": {"runway_date_before": "2026-10-10", "runway_date_after": "2026-10-10",
              "lasts_past_target": false, "days_gained": 0,
              "gap_before": 425.9, "gap_after": 371.21, "min_balance_after": -271.21,
              "clears_the_gap": false},
   "in_plan": true,
   "effect_with_plan": {"runway_date_after": null, "lasts_past_target": true, "days_gained": 21,
                        "gap_after": 0.0, "min_balance_after": 128.79, "clears_the_gap": true}},
  {"id": "cancel_…", "type": "cancel_subscription", "label": "Cancel Streaming before the trial ends", "…": "…"}
]}
```

`label_parts` carries the label's structured pieces, for translation.

### `GET /api/scenarios`

`{"scenarios": [{"key": "fake_landlord", "persona": "ana", "kind": "transfer",
"title": "Fake landlord deposit", "expect": "pause", "amount": 800.0,
"description": "URGENT apartment deposit - pay today or you lose the place", …}, …]}`

### `POST /api/users/{user}/affordability`

Body: `{"amount": 47.34, "when": "2026-09-13"}`. `when` is optional (alias
`date`); other fields are ignored.

```json
{
  "amount": 47.34, "when": "2026-09-13", "affordable": false,
  "runway_date_before": "2026-10-10", "runway_date_after": "2026-10-10", "days_lost": 0,
  "min_balance_after": -373.24, "min_balance_date_after": "2026-10-31", "gap_after": 473.24,
  "max_safe_amount": 0.0, "max_safe_through": "2026-10-31", "max_without_moving_runway": 49.38,
  "already_short": true,
  "if_you_fix_first": {"plan": ["Cap dining at $12 a week", "Move $400 from savings"],
                       "max_safe_amount": 28.78, "max_safe_through": "2026-10-31",
                       "runway_date_after": null, "closes_the_gap": true},
  "reason": "Not yet. Your money already runs out on 2026-10-10, before your flight, so nothing is genuinely spare. …"
}
```

### `POST /api/transfers/check`

Either a seeded scenario:

```json
{"scenario": "fake_landlord"}
```

or a transfer described directly (`user` defaults to `ana`):

```json
{"user": "ana", "amount": 800, "payee_id": "…", "payee_name": "Michael Reyes", "description": "URGENT deposit"}
```

Response:

```json
{
  "amount": 800.0, "payee": "Michael Reyes", "risk_score": 84, "pause": true, "verdict": "pause",
  "reasons": ["You have never sent money to this payee", "This is 52% of your checking balance", "…"],
  "questions": ["Did someone contact you and pressure you to pay right now?", "…"],
  "signals": [{"code": "new_payee", "points": 30, "reason": "…", "detail": "first payment to this account"}],
  "known_payee": false, "runway_date_after": "2026-10-01", "scenario": "fake_landlord"
}
```

Nothing is sent; this only scores.

### `POST /api/chat`

Body: `{"user": "ana", "message": "¿Puedo permitirme ir a Chicago este finde? Unos 250$", "language": "es"}`.
`language` is optional; by default the reply matches the language of the
message. Optional headers carry the user's own model key; see
[agent.md](agent.md#bring-your-own-key).

```json
{
  "reply": "Ahora mismo no …",
  "language": "es",
  "used_tools": ["get_summary", "check_affordability", "suggest_fixes", "propose_transfer"],
  "proposed_action": {
    "id": "act_3f9c2a71b0", "type": "transfer", "from": "savings", "to": "checking",
    "amount": 400.0, "label": "Move $400 from savings",
    "effect": {"runway_date_before": "2026-10-10", "gap_before": 425.9,
               "runway_date_after": "…", "gap_after": "…", "measured": true,
               "measured_by": "backend.engine"}
  },
  "_mode": "llm", "_provider": "gemini", "_key_source": "server"
}
```

| Field | Meaning |
|---|---|
| `used_tools` | Every tool called this turn, in order. The audit trail for "where did that number come from" |
| `proposed_action` | A staged action to show as an approval card, or `null` |
| `_mode` | `llm` or `scripted`: who actually answered |
| `_provider` | `gemini`, `anthropic`, `openai` or `scripted` |
| `_key_source` | `user`, `server`, or `null` if no model answered |
| `_fell_back` | Present when the model path failed: a one-line reason |
| `_key_rejected` | `true` when the user's own key is the reason |

### `POST /api/actions/propose`

Stages an action exactly as the agent would. Body is either
`{"user": "ana", "action": {…}}` or the action itself with `user` alongside.

| `type` | Fields | On confirm |
|---|---|---|
| `transfer` | `amount`, `from` (`savings`), `to` (`checking`), `label` | Moves money between the user's accounts in the cache; best-effort write to Nessie |
| `spending_cap` | `category`, `weekly_cap`, `amount` (estimated savings), `label` | Saved in `meta.spending_caps`. Ours; Nessie has no equivalent |
| `bill_payment` | `amount` | Debits checking in the cache |
| `freeze_card` | `reason` | Sets `is_frozen` on the credit card. Simulated |

It returns the stored record with `id` (`act_…`), `status: "proposed"` and a
measured `effect`: `runway_date_before`, `gap_before`, `runway_date_after`,
`gap_after`, `min_balance_after`, `measured`, `measured_by`, `measured_note`.
An effect that cannot be measured has `runway_date_after: null` and a note. It
never echoes an unchanged date.

### `POST /api/actions/{id}/confirm`

Body: `{"user": "ana", "action": { …the proposed_action… }}`. The action is
optional, but send it. Proposed actions live **in memory**; if the API
restarted between propose and confirm, the gate rebuilds the action from what
you post.

```json
{
  "id": "act_3f9c2a71b0", "status": "executed",
  "message": "Moved $400.00 from savings to checking. No NESSIE_API_KEY set, so the transfer stayed in the local cache.",
  "runway_date_after": null, "executed_in_nessie": false,
  "action": { "…the record, now status executed…": "" }
}
```

- `status` is `executed` or `failed` (unknown and expired id, insufficient
  balance, missing account).
- Confirming twice returns `duplicate: true` and moves nothing.
- `executed_in_nessie` is `true` only if Nessie accepted the write. Caps,
  freezes and bill payments are always local.

**This is the only code path that changes a balance.** Approving really moves
money in the cache; reset between rehearsals.
