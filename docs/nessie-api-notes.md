# Nessie: what we assumed, and what has to be verified

**Owner: P1. Deadline: first hour.** Everything below marked ❓ is from the docs and
from memory, not from a live call. Confirm each one against the sandbox, edit this
file, and tell the team in the channel. These are the details that cost hours if
they turn out different at hour 14.

## Access

| Thing | Value |
|---|---|
| Base URL | `http://api.nessieisreal.com` |
| Auth | `?key=<API_KEY>` as a query parameter, on every request |
| Key | from the developer portal at nessieisreal.com, into `.env` as `NESSIE_API_KEY` |

Check reachability without seeding anything:

```bash
python -c "from backend.nessie.client import NessieClient; print(NessieClient().ping())"
```

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

## ❓ Verify these first

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
6. **Merchant category.** We send a list (`"category": ["groceries"]`). Confirm it is
   not a plain string.
7. **Bill status values.** We send `"recurring"`. Confirm the accepted set.
8. **Bulk delete.** Does `DELETE /data?type=Customers` exist? We do not rely on it —
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

Nessie also has no webhooks, so `sync.py --watch` polls.
