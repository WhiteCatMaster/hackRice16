# Nessie API notes

What Capital One's Nessie sandbox actually does, as established by probing and by
a full live seed on 2026-09-11 and 2026-09-12. It also records what we built
around it. Read this before running anything with `--push`.

## Access

| | |
|---|---|
| Base URL | `https://api.nessieisreal.com`. **HTTPS only**: `http://` is refused at the TCP level (`Connection refused`, no redirect) |
| Auth | `?key=<API_KEY>` query parameter on every request |
| Key | From nessieisreal.com, into `.env` as `NESSIE_API_KEY` |
| Reads | **Not gated.** `GET /customers` returns `200` for any key, including none |
| Writes | **Gated.** `POST` without a valid key returns `401 Invalid API key.` The key is checked before the body, so an empty `POST` tests a key without creating anything |

```bash
python -c "from backend.nessie.client import NessieClient; print(NessieClient().check_access())"
curl -s 'localhost:8000/api/health?probe=1'     # the same check, through the API
```

`check_access()` returns `{reachable, authorized, detail}`. A bare "key is
present" check is worthless, since reads pass with no key at all.

## Endpoints we use

| Resource | Endpoints | For |
|---|---|---|
| Customers | `POST /customers`, `GET /customers` | Personas and counterparties |
| Accounts | `POST/GET /customers/{id}/accounts`, `DELETE /accounts/{id}` | Checking, savings, credit card; teardown |
| Merchants | `POST /merchants`, `GET /merchants` | Categories and coordinates for risk |
| Purchases | `POST/GET /accounts/{id}/purchases` | Spending history, card-testing scenario |
| Bills | `POST/GET /accounts/{id}/bills` | Rent, phone, insurance, gym, streaming |
| Deposits | `POST/GET /accounts/{id}/deposits` | Money from home, stipend, payroll |
| Withdrawals | `POST/GET /accounts/{id}/withdrawals` | Bills already paid, tuition |
| Transfers | `POST/GET /accounts/{id}/transfers` | Savings moves, roommate, scam transfers, approved actions |

Seven resource types, read and written.

## Verified behaviour

| Topic | What the sandbox does | What we do |
|---|---|---|
| Merchant `category` | A plain string (`"pharmacy"`), not a list | `seed.py` sends what the API accepts |
| `geocode` | `{lat, lng}` | Matches |
| `address` | `{street_number, street_name, city, state, zip}` | Matches |
| `BillCreate` | Rejects `creation_date` as an extra field | Dropped; the server sets it |
| `PurchaseCreate` | `medium` must be `balance` or `rewards`; `credit` is rejected | `seed.api_medium()` maps `credit → balance` on the way out; the cache keeps `credit` |
| `TransferCreate` | Accepts only `transaction_date`, `status`, `amount`, `description`. Rejects `medium` and `payee_id` in the body, and **silently ignores** `payee_id` as a query parameter | See [A transfer cannot name its payee](#a-transfer-cannot-name-its-payee) |
| Empty sub-collection | `GET /accounts/{id}/transfers` with none answers `404 "No transfers found…"`, not `[]` | `client.collection()` treats 404 as empty on all list endpoints |
| `DELETE /customers/{id}` | `403 "Missing Authentication Token"`: API Gateway's phrasing for *no such route* | Teardown deletes accounts instead |
| `PUT` balance corrections | Accepted, then ignored: balances are recomputed from transactions | See [Balances are not ours](#balances-are-not-ours) |
| Sandbox contents | Ships its own branches, ATMs and a few merchants; shared with other teams | Sync must not assume every customer is ours |

To discover a schema, post an empty body: validation fails before anything is
created, and the error lists the required fields.

### A transfer cannot name its payee

A live transfer records only its payer. But "have you paid this person before?"
is the signal the whole scam demo turns on. It is rebuilt from
`transfers.payee_id` by `db.rebuild_payees()`. Once, a sync that took Nessie at
face value blanked that column. Ana's `legit_roommate` transfer, the
false-positive control, then started scoring **pause**.

`sync.py` now re-attaches `payee_id` and `medium` from the deterministic
generator via `id_map`, the same way every other local-only field is restored.

### Balances are not ours

After a full push, Ana's checking read **$56.00** upstream against a calibrated
$1,552.93. `reconcile_balances()` sends `PUT` corrections, every account reports
`(corrected)`, and the next run shows identical deltas.

So **`python -m backend.nessie.sync --source nessie` cannot reproduce the demo.**
Pulling it into the cache once moved Ana's runway from 2026-10-10 to 2026-09-13,
put her card at 107% utilization and her daily spend at $0.00. The default
`--source local` is unaffected. Every read goes through the cache, so the app is
insulated by design. `seed.reset_demo` undoes a bad sync in about a second.

### Teardown leaves customer shells

`seed.reset_demo --push` deletes only objects recorded in `id_map`, and only
**accounts**, which takes their transactions with them. Customers cannot be
deleted, so one empty set of customer records accumulates per push. Before this
was understood, teardown deleted nothing, and every push added a full duplicate
dataset (about 1,200 objects).

`db.wipe()` deliberately keeps `id_map`. It is the only record of what exists
upstream; clearing it on a local reset would strand those objects beyond the
teardown's reach. Only the Nessie teardown clears it, after the deletes.

## Still unverified

`python -m seed.probe_nessie` creates a throwaway customer, tests assumptions,
deletes what it can, and writes `docs/probe-results.json`. The committed results
are from a run without a working write key, so these write-side questions are
still open:

1. **Date granularity.** We assume `purchase_date` is day-only, and keep times
   ourselves (below).
2. **Credit limit field.** We assume Credit Card accounts have none, and store
   our own.
3. **Overdrafts.** We assume a transaction that takes an account negative is
   rejected. `seed.py` opens accounts with exactly enough float to avoid it.
4. **Credit-card sign.** Whether a purchase decreases a card's balance like any
   other account.
5. **Create response.** We handle both `{code, message, objectCreated: {_id}}`
   and a bare object.
6. **Bill status values.** We send `recurring`.
7. **Bulk delete** (`DELETE /data?type=…`). We do not rely on it.

## Workarounds

### Intra-day timestamps

Velocity ("five charges in 24 minutes") and impossible travel ("95 minutes
later") need a time of day. `backend/nessie/timestamps.py` stores ours in the
one free-text field Nessie round-trips:

```
"Hy-Vee"  →  "Hy-Vee [t=18:41]"
```

`encode()` runs on push, and `decode()` strips it on sync into `occurred_at`. The
tag never reaches a screen.

### Opening floats

Credit-card purchases, and Raj's tuition landing before his first stipend, would
overdraw an account. `seed.opening_floats()` walks each account's timeline and
opens it with exactly its worst-point headroom. Reconciliation then tries to
remove it.

### Push order and resuming

Transactions are pushed chronologically, funding deposits first. Every created
id goes into `id_map` immediately, so `seed.seed --push --resume` continues an
interrupted run instead of duplicating it.

## Things Nessie has no concept of

Stored in SQLite, labelled `_simulated` where they appear in payloads:

| Ours | Where |
|---|---|
| Credit limit, APR, statement day | `accounts.credit_limit`, `.apr`, `.statement_day` |
| Card freeze | `accounts.is_frozen`, `.frozen_reason` |
| Intra-day timestamps | `occurred_at` on purchases, deposits, withdrawals, transfers |
| Merchant risk tags | `merchants.risk_tag` |
| Fraud and scam labels | `purchases.label`, `transfers.label` |
| Home currency and FX rate | `customers.home_currency`, `.fx_rate` |
| Known-payee history | `payees` table |
| Who a transfer paid | `transfers.payee_id` |
| Spending caps | `meta.spending_caps` |

Nessie has no webhooks either; `sync.py --watch N` polls.
