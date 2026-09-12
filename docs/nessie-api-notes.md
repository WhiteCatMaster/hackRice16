# Nessie: what we assumed, and what has to be verified

**Owner: P1. Deadline: first hour.** Everything below marked ❓ is from the docs and
from memory, not from a live call. Confirm each one against the sandbox, edit this
file, and tell the team in the channel. These are the details that cost hours if
they turn out different at hour 14.

## Access

| Thing | Value |
|---|---|
| Base URL | `https://api.nessieisreal.com` — **HTTPS only** |
| Auth | `?key=<API_KEY>` as a query parameter, on every request |
| Key | from the portal at nessieisreal.com, into `.env` as `NESSIE_API_KEY` |

**`http://` does not work.** It is refused at the TCP level, not redirected, so you
get `Connection refused` rather than anything that hints at the cause. This cost us
an hour; it is the first thing to check if nothing connects.

Check reachability without seeding anything:

```bash
python -c "from backend.nessie.client import NessieClient; print(NessieClient().ping())"
```

## Answering the ❓ questions

Do not answer them by reading. Run the probe:

```bash
python -m seed.probe_nessie
```

It creates one throwaway customer with its own accounts and merchant, tests all
eight questions against the live API, deletes everything it made, and prints
MATCHES / DIFFERS / UNKNOWN per question with the code change each DIFFERS needs.
It never touches seeded demo data and it never runs a bulk delete. Results are
saved to `docs/probe-results.json`.

## Endpoints we use

| Resource | Endpoint | Used for |
|---|---|---|
| Customers | `POST /customers`, `GET /customers` | one per persona, plus the scam counterparties |
| Accounts | `POST /customers/{id}/accounts`, `GET /customers/{id}/accounts` | checking, savings, credit card |
| Merchants | `POST /merchants`, `GET /merchants` | categories and coordinates for the risk engine |
| Purchases | `POST /accounts/{id}/purchases` | spending history and the card-testing scenario |
| Bills | `POST /accounts/{id}/bills` | recurring rent, phone, insurance, gym, card payment |
| Deposits | `POST /accounts/{id}/deposits` | money from home, stipend, payroll |
| Withdrawals | `POST /accounts/{id}/withdrawals` | bills already paid, tuition |
| Transfers | `POST /accounts/{id}/transfers` | savings moves, paying a roommate, the scam transfers |

Seven resource types, reads and writes. That is the "creative use of the API" slide.

## ✅ Confirmed against the live API

Verified on 2026-09-11 by `python -m seed.probe_nessie`, with no key.

| # | Question | Answer |
|---|---|---|
| — | Protocol | **HTTPS only.** `http://` is refused at the TCP level |
| — | Are reads gated? | **No.** `GET /customers` returns `200 []` for any key, including an empty one |
| — | Are writes gated? | **Yes.** `POST` without a valid key returns `401 Invalid API key.` |
| — | Key check order | The key is checked **before** the body, so an empty `POST` tests the key without creating anything |
| 6 | Merchant `category` shape | **A plain string**, not a list. Live data returns `"Comida"`. `seed.py` now negotiates both |
| 6.1 | `geocode` shape | `{lat, lng}` — matches what we send |
| 6.2 | `address` shape | `{street_number, street_name, city, state, zip}` — matches what we send |

The sandbox ships with its own readable data — 207 branches, 13 ATMs, 4 enterprise
merchants — and `/customers`, `/accounts` and `/merchants` are globally empty. That
data is how the questions above got answered without a key.

## ❓ Still open — these need a key

Everything below is a **write** question, so no amount of reading answers it. Get a
key, then `python -m seed.probe_nessie` answers all of them in one run.

1. **Date granularity.** Is `purchase_date` day-only (`2026-09-11`) or a full
   timestamp? We assume day-only. If we are wrong, drop the workaround below.
2. **Credit limits.** Does a `Credit Card` account accept a limit field? We assume
   not, and store our own.
3. **Overdrafts.** Does Nessie reject a withdrawal or purchase that takes an account
   negative? We assume yes and handle it (see *Opening floats*).
4. **Credit-card sign.** Does a purchase on a `Credit Card` account *decrease* its
   balance? We assume Nessie treats every account the same way and has no notion of
   a card balance being debt.
5. **Create response shape.** We handle both `{code, message, objectCreated:{_id}}`
   and a bare object; confirm which one you get.
6. **Bill status values.** We send `"recurring"`. Confirm the accepted set.
7. **Bulk delete.** Does `DELETE /data?type=Customers` exist? We do not rely on it —
   `reset_demo.py` deletes only the objects in our own `id_map`.

## Workarounds we built, and why

### Intra-day timestamps

Nessie dates are day-level ❓. Velocity ("five charges in twenty minutes") and
impossible travel ("Omaha then Miami 95 minutes later") are meaningless without a
time of day. We smuggle ours through the `description` field:

```
"Hy-Vee"  ->  "Hy-Vee [t=18:41]"
```

`backend/nessie/timestamps.py` encodes on the way out and strips on the way back,
so `occurred_at` reaches the engine and the tag never reaches a screen.

### Opening floats

Nessie rejects transactions that overdraw ❓. Two things in our data legitimately
would: credit-card purchases, and Raj's tuition payment landing before his first
stipend. So `seed.py` walks each account's timeline, finds its worst point, and
opens the account with exactly that much headroom. The reconciliation step at the
end of the seed removes it again with a `PUT`.

### Balance reconciliation

After seeding, we `GET` every account and compare Nessie's computed balance against
what the demo needs, then `PUT` the correction. The printed `delta` is the honest
signal: **delta 0.00 means Nessie's arithmetic agrees with ours.** A non-zero delta
on the credit card is expected and tells you assumption 4 above is wrong.

### Things Nessie has no concept of

Stored by us, in SQLite, and labelled `_simulated` in every API payload so the pitch
can say so out loud:

| Ours | Where |
|---|---|
| Credit limit, APR, statement day | `accounts.credit_limit`, `.apr`, `.statement_day` |
| Card freeze | `accounts.is_frozen`, `.frozen_reason` |
| Intra-day timestamps | `purchases.occurred_at` and friends |
| Merchant risk tags | `merchants.risk_tag` |
| Fraud/scam labels | `purchases.label`, `transfers.label` |
| Home currency and FX rate | `customers.home_currency`, `.fx_rate` |
| Known-payee history | the `payees` table |
| **Who a transfer was paid to** | `transfers.payee_id` — see below |

Nessie also has no webhooks, so `sync.py --watch` polls.


## What the live API actually rejected (2026-09-12, first real seed)

The probe caught the merchant `category` shape. These four only surfaced on a real
push, each as a `400` that stopped the seed dead. All are fixed at the push
boundary; the local dataset is unchanged.

| Endpoint | Rejected | Fix |
|---|---|---|
| `BillCreate` | `creation_date` — *extra fields not permitted* | Dropped; the server sets it. `payment_date` already fell back to it. |
| `PurchaseCreate` | `medium: "credit"` — enum is `balance\|rewards` only | `seed.api_medium()` maps `credit → balance` on the way out. The account is already a Credit Card upstream. |
| `TransferCreate` | `medium` **and** `payee_id` — *extra fields not permitted* | Both dropped. |
| account balances | corrections don't stick | See below. |

Post an empty body to any endpoint to get its real schema back — validation fails
before anything is created, so the error lists exactly the required fields.

### A transfer cannot name its payee

`TransferCreate` accepts only `transaction_date`, `status`, `amount`, `description`.
Passing `payee_id` as a query parameter is **accepted and silently ignored**: the
transfer is created, `GET /transfers/{id}` returns no payee, and it appears only
under the payer's account.

This matters more than it looks. `rebuild_payees()` reconstructs known-payee history
from `transfers.payee_id`, and "have you paid this person before?" is the signal the
whole scam demo turns on. A sync that took Nessie at face value blanked that column
and Ana's **legit roommate transfer started scoring PAUSE** — the false-positive
control case, failing. `sync.py` now re-attaches `payee_id` and `medium` from the
deterministic generator via the `id_map`, the same way every other local-only field
is restored.

### This sandbox's balances are not ours

It recomputes account balances from the transactions it holds and ignores the `PUT`
corrections `reconcile_balances()` sends — every account reported `(corrected)` on
two consecutive runs with identical deltas, and the live balances stayed wrong. After
a full push Ana's checking read **$56.00** upstream against a calibrated $1,552.93.

So **`sync --source nessie` cannot reproduce the demo** and must not be run before
one. Pulling it into the cache once moved Ana's runway from 2026-10-10 to 2026-09-13,
put her card at 107% utilization and dropped her daily spend to $0.00. `seed.reset_demo`
restores everything in ~0.1s.

The default `--source local` is unaffected, and every read in the app goes through the
cache, so the demo is insulated from all of this by design.


### There is no way to delete a customer

`DELETE /customers/{id}` answers **403 `{"message":"Missing Authentication Token"}`** —
API Gateway's phrasing for *no such route*, not an auth problem; the same key deletes
accounts fine. So `delete_seeded_from_nessie()`'s original premise, that removing a
customer cascades to its accounts and transactions, never held here: every teardown
deleted nothing and reported success, and the next `--push` created a second full copy
of the dataset upstream. That is exactly how ~1,200 objects accumulated.

It now deletes **accounts**, which does work and does take their transactions along.
Customer shells are left behind because the API offers no way to remove them — they are
empty and harmless, but they accumulate one set per seed.

### An empty sub-collection is a 404

`GET /accounts/{id}/transfers` returns **404 `"No transfers found for this account"`**
when there simply are none, rather than `[]`. Most accounts have no transfers, so the
post-seed `sync_from_nessie()` aborted partway through and left the cache
half-populated — 20 customers (duplicates, plus other teams' from the shared sandbox)
and Ana's checking at $56.00. `client.collection()` now treats 404 as the empty list for
all six list endpoints.

### Guard rail

`db.wipe()` keeps `id_map`. It records *remote* state — the only list of what we created
in Nessie — so clearing it on a local-only reset leaves every seeded object alive and
untracked upstream, beyond the reach of the teardown. Only the Nessie teardown clears it,
after the deletes.
