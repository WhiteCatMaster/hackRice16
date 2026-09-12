# Capital One: Best Use of Nessie. Project Plan

> Working name: **Landed**, a financial copilot for international students in their first year in the US, with built-in scam protection.

## Contents

1. [The challenge](#1-the-challenge)
2. [Ideas we considered](#2-ideas-we-considered)
3. [Idea A: Fraud and scam detection](#3-idea-a-fraud-and-scam-detection)
4. [Idea B: First-year-in-the-US copilot](#4-idea-b-first-year-in-the-us-copilot)
5. [Recommendation: combine them](#5-recommendation-combine-them)
6. [Architecture](#6-architecture)
7. [Team plan for 4 people](#7-team-plan-for-4-people)
8. [Timeline](#8-timeline)
9. [Demo script](#9-demo-script)
10. [Pitch outline](#10-pitch-outline)
11. [Risks and mitigations](#11-risks-and-mitigations)
12. [Appendix A: Seed data spec](#appendix-a-seed-data-spec)
13. [Appendix B: Team split if we build pure fraud detection](#appendix-b-team-split-if-we-build-pure-fraud-detection)

---

## 1. The challenge

### What Capital One is asking

Capital One sponsors **Nessie**, a mock banking API. It behaves like a real bank's backend, but all the data is fake, so we can build a financial app without real money or real customer data. The challenge is to build the most creative and useful app on top of it, one that "empowers users and improves their financial lives."

### What Nessie gives us

Nessie is a REST API with read and write access (GET, POST, PUT, DELETE). The API key is passed as a query parameter. Get the key and the current base URL from the Nessie developer portal (nessieisreal.com) and check the docs there, since field names below are from memory.

| Resource | What it contains | How we use it |
|---|---|---|
| Customers | People with name and address | One customer per demo persona |
| Accounts | Checking, Savings, Credit Card, with balances | Balances, runway, credit utilization |
| Purchases | Card transactions tied to a merchant, with amount, date, status | Spending patterns, daily burn rate, anomaly features |
| Merchants | Name, category, address, geocode (lat/lng) | Categories for budgeting, location for anomaly detection |
| Bills | Payee, amount, payment date, recurring date, status | Forecasting fixed costs, bill explanations |
| Deposits / Withdrawals | Money in and out of an account | Lump-sum income from home, cash usage |
| Transfers | Money between accounts, including to other customers (P2P) | Savings moves, scam interception on new payees |
| Loans | Loan records attached to accounts | Optional: student loan context |
| ATMs / Branches | Physical locations with coordinates | Optional: "nearest fee-free ATM" |

### Practical facts about Nessie that shape the design

- **The sandbox starts nearly empty.** We need a seed script that creates customers, accounts, and months of realistic history. This is the first thing to build.
- **No webhooks.** To react to new transactions, we poll and keep our own local copy.
- **Dates are probably day-level only.** Verify in the first hour. If there is no time of day, we keep precise timestamps in our own database (or in the description field).
- **It can be slow or flaky.** Cache everything locally so the demo never depends on Nessie responding live.
- **Some banking concepts don't exist in Nessie** (credit limits, credit scores, card freezes). We store or simulate them ourselves and say so openly in the pitch.

### What the judges will likely look for

1. **A real problem.** Financial wellness, not just a prettier balance screen.
2. **Creative, meaningful use of the API.** Several endpoint types working together, including write operations, not a single GET call.
3. **A convincing demo.** A clear user, a clear pain point, and a two-to-three-minute flow where the app visibly helps.

---

## 2. Ideas we considered

| # | Idea | One-line summary | Verdict |
|---|---|---|---|
| 1 | First-year-in-the-US copilot | Forecasting and explanations for international students new to US banking | **Core product** |
| 2 | Cash-flow / overdraft predictor | Day-by-day balance projection with fixes for danger days | Merged into #1 as the runway forecast |
| 3 | Location-aware spending | Map of where money goes, budget-aware local discovery | Nice extra, not core |
| 4 | Fraud and scam detection | Personal anomaly detection plus pre-transfer scam interception | **Scam interception merged into #1** |
| 5 | Group money / settle-up | Split shared bills and settle with transfers | Common idea, skip |
| 6 | Caregiver scam shield | Trusted contact approves risky transfers | Absorbed into #4 as a stretch goal |
| 7 | Hardware "impulse brake" | Physical device showing a purchase's budget impact | Fun wildcard, high risk |

---

## 3. Idea A: Fraud and scam detection

### Concept

The app watches every purchase and transfer on a user's accounts, learns what "normal" looks like for that specific person, and flags anything that doesn't fit. Every flag comes with a plain-language reason ("6× your usual amount, at a merchant you've never used, 900 km from your last purchase"). The user answers "that was me" or "not me," and the system learns from the answer.

Fraud detection is a common hackathon theme and it is Capital One's home territory, so the idea alone won't win. Execution and differentiators will.

### Features we can engineer from Nessie data

| Feature | Source | Why it matters |
|---|---|---|
| Amount z-score per category, per user | Purchases + merchant category | Catches unusually large purchases relative to the user's own habits |
| New merchant flag | Purchases history | Fraud often happens at merchants the user has never used |
| Distance from home and from previous purchase | Merchant geocode | Detects "impossible travel" and out-of-area use |
| Velocity (purchases per day, bursts of tiny amounts) | Purchases | Card-testing attacks use many small charges |
| Category shift | Merchant category | Someone who never buys electronics suddenly buys three laptops |
| Share of balance consumed | Account balance | A purchase draining 80% of the account is meaningful |
| New payee on a transfer, amount relative to balance | Transfers | Core signal for scam payments |

### Model design

We have no labeled real fraud, so we start unsupervised and make it personal rather than global.

1. **Rules layer.** Impossible travel, card-testing bursts, large transfers to new payees. Fast, explainable, and makes the demo reliable.
2. **ML layer.** An Isolation Forest per user is the quick win. A stronger option is a small PyTorch autoencoder trained on each user's normal transactions, where high reconstruction error means "this doesn't look like you."
3. **Combined risk score (0–100)** with the top contributing features attached. Those features become the explanation.

Because we generate the data ourselves, we can inject labeled fraud and report metrics such as detection rate at a fixed false-positive rate. We must present these clearly as results on synthetic data.

### Differentiators

- **Intercept before, not after.** Check a transfer *before* it goes through. If a user is about to send $900 to a new payee, the app pauses and asks: "Did someone contact you and pressure you to pay? Government agencies never ask for payment this way." This targets authorized push-payment scams, which card-fraud models miss entirely.
- **"Your normal" as a visual.** A map of the user's usual area, typical amounts per category, and regular merchants. Flagged transactions visibly fall outside that shape.
- **A feedback loop.** Each "that was me" adjusts the user's baseline, so after confirming a trip to Chicago, purchases there stop triggering alerts.
- **Plain-language explanations.** An LLM turns the top features into one clear sentence.
- **Trusted contact (stretch).** An optional family member must approve risky transfers.

### Simulating "Not me"

Nessie has no card-freeze endpoint. We simulate it by updating or deleting the purchase, creating a refund deposit, and storing a "frozen" flag in our own database.

---

## 4. Idea B: First-year-in-the-US copilot

### Concept

International and exchange students arrive in the US with money but no map. They don't know how credit scores work, why a card's current balance differs from what's due this month, when rent actually leaves the account, or why a $12 menu item costs $16 after tax and tip. Most banking apps assume the user already understands the US system. Ours assumes they don't.

The app reads the student's accounts, bills, and spending, forecasts where their money is going, and explains everything in plain language, in their own language if they want. When something needs doing, it can do it through Nessie (move money, schedule a payment), always after the user confirms.

**Why it's a strong pitch:** one of us is on exchange at Creighton right now. We can open with a real problem we have lived, which lands much better than an imagined user.

### Why this persona fits Nessie well

- **Lump-sum income.** Money arrives in large, irregular deposits (a transfer from parents, a scholarship, a stipend). The key question is not "am I on budget this month?" but "does this money last until I fly home?" That maps to **Deposits**.
- **Fixed recurring bills.** Rent, phone, health insurance, gym. That maps to **Bills**.
- **A first credit card.** Many start with a student card and don't know how to build credit with it. That maps to **Credit Card accounts** and **Purchases**.
- **Two currencies in their head.** They think in euros, pesos, or rupees but spend in dollars.
- **A known end date.** The semester ends and there's a flight home, which makes forecasting concrete and the demo easy to follow.

### Features

**Runway forecast (technical core).** Takes current balances, upcoming bills, expected deposits, and average daily spending per category, and projects the balance day by day until the end of the semester. The output is one number that matters: *"At your current pace, your money lasts until April 18. Your flight home is May 10."* Then it shows what would close the gap. This needs a solid recurring-transaction detector and category spending averages, not deep ML.

**The agent.** A chat where the student asks "Can I afford a weekend in Chicago?" or "Why did my card balance go up if I paid it?" The LLM has tools mapped to Nessie endpoints and to our forecast engine, and answers with real numbers: *"Yes, if you keep it under $250. Rent is due on the 1st and you'd still have a $180 buffer."*

**Bill decoder.** Explains every bill: what it is, when it hits, whether the amount is normal, what happens if it's late. Flags surprises like a free trial about to become a paid subscription.

**Credit builder.** Explains the student's card using their real usage: utilization, statement balance vs. current balance, and why paying in full and on time matters. Nessie has no credit limit or credit score, so we store the limit ourselves and label any score projection as an educational estimate, never a real FICO score.

**Home-currency view.** A toggle showing amounts and runway in the home currency. Small to build, but it makes the app feel designed for this user. A fixed, cached exchange rate is fine for the demo.

**Scam pause (from Idea A).** International students are a known target for scams where someone impersonates immigration officials or tax authorities and demands payment. If the student is about to send a large transfer to a new payee, the app pauses and asks questions first.

### The main risk

Judges may see "a chatbot wrapper over a bank API." Three things counter that:

1. The forecast engine is real logic that works without the LLM.
2. The agent takes real actions through Nessie instead of only answering.
3. The persona is specific enough that every feature has a clear reason to exist.

If we must cut something under time pressure, we cut chat polish, never the forecast.

---

## 5. Recommendation: combine them

We build **Idea B as the main product** and include the **pre-transfer scam interception from Idea A** as one of its features. Optionally, if time allows, we add the purchase anomaly detector too.

This gives us:

- **A specific persona and a personal story** (from B).
- **A deterministic technical core** that can be explained and tested: the runway forecast (from B).
- **An ML/risk component** that shows depth: scam and anomaly scoring (from A).
- **Wide, meaningful use of Nessie:** customers, accounts, purchases, merchants, bills, deposits, and transfers, with both reads and writes.
- **Two strong demo moments:** the runway line turning from "short" to "safe" after one approved action, and a scam transfer being stopped before the money leaves.

---

## 6. Architecture

### Overview

```
                 ┌────────────────────────┐
                 │   Nessie API (mock)    │
                 └───────────▲────────────┘
                             │ REST (GET/POST)
        ┌────────────────────┴────────────────────┐
        │  Nessie client + sync worker (polling)  │
        │  local cache / database (SQLite)        │
        └───────┬──────────────────────┬──────────┘
                │                      │
      ┌─────────▼─────────┐  ┌─────────▼──────────┐
      │  Engine           │  │  Agent             │
      │  - recurring      │  │  - LLM tool calls  │
      │    detection      │◄─┤  - explanations    │
      │  - runway forecast│  │  - proposes actions│
      │  - affordability  │  └─────────┬──────────┘
      │  - scam / anomaly │            │
      └─────────┬─────────┘            │
                │                      │
        ┌───────▼──────────────────────▼──────────┐
        │        Backend API (FastAPI)            │
        │  confirmation gate for write actions    │
        └───────────────────▲─────────────────────┘
                            │ JSON
        ┌───────────────────┴─────────────────────┐
        │ Frontend (web app, or Android in Kotlin)│
        │ Dashboard · Runway · Chat · Bills ·     │
        │ Credit · Alerts                          │
        └─────────────────────────────────────────┘
```

### Stack

| Layer | Choice | Notes |
|---|---|---|
| Seed data | Python script | Creates personas, history, and scam scenarios in Nessie |
| Backend | Python + FastAPI | One language for data, engine, and agent |
| Storage | SQLite | Local cache of Nessie data plus our own fields (limits, frozen flags, timestamps) |
| Engine | pandas, scikit-learn (optional PyTorch) | Forecast is deterministic; ML only for anomaly scoring |
| Agent | LLM API with tool calling | Tools map to Nessie reads, engine functions, and proposed writes |
| Frontend | Web (React/Next or similar) or Android (Kotlin) | Web is faster to build; Android gives native notifications |

### Design rules (non-negotiable)

1. **The LLM never calculates numbers.** The backend computes balances, forecasts, and affordability. The LLM only picks tools and explains results. This prevents the agent from inventing a balance in front of the judges, and we say this in the pitch.
2. **Every write needs user confirmation.** The agent *proposes* an action. The user taps "Approve." Only then does the backend call Nessie's POST endpoint.
3. **The demo never depends on Nessie being live.** All reads go through the cache. A reset script restores the demo state in one command.
4. **Be honest about simulations.** Credit limits, card freezes, and credit score estimates are ours, not Nessie's, and we label them as such.

### How the forecast works (spec for the engine)

1. **Starting point:** current checking balance (savings shown separately as a reserve).
2. **Recurring detection:** group purchases and bills by merchant or payee; a series is recurring if amounts are similar (within about 10%) and intervals are roughly weekly, biweekly, or monthly.
3. **Known future events:** bills on their due or recurring dates; expected deposits entered by the user or detected as recurring.
4. **Variable spending:** daily burn rate per category from the last 30 days (median is more robust than mean), optionally different for weekdays and weekends.
5. **Projection:** step day by day until the target date (flight home).
6. **Outputs:** the daily balance series, the **runway date** (first day the balance drops below zero or below a safety buffer), and the **gap** (money needed to reach the target date).
7. **Affordability:** re-run the projection with a hypothetical expense and report the new runway date and the lowest buffer.
8. **Fixes:** candidate actions the user can approve, such as a transfer from savings, a weekly category cap, or cancelling a detected subscription.

### How the scam check works (spec for the engine)

Before a transfer is executed, the engine returns a risk score and reasons. Suggested signals:

- The payee has never received money from this user.
- The amount is large in absolute terms or relative to the balance.
- It's a round amount.
- There have been several transfers or purchases in a short burst.
- The merchant category is gift cards or money transfer services.
- The user's description contains urgency words ("urgent," "fine," "immigration," "IRS," "police").

Above a threshold, the app pauses the transfer and asks two or three questions before letting the user continue or cancel. If the purchase anomaly detector is built (stretch goal), it shares the same explanation format.

---

## 7. Team plan for 4 people

### Principle: split by layer, connect by contract

Each person owns one layer end to end. In the first two hours, the whole team agrees on **data schemas and API contracts**, so everyone can build in parallel against mock data and integrate later without surprises.

### Roles at a glance

| Person | Role | Owns | Key deliverable |
|---|---|---|---|
| **P1** | Data & Nessie integration | Seed script, Nessie client, sync worker, cache, reset script | Realistic demo data in Nessie and a reliable local copy |
| **P2** | Engine (forecast & risk) | Recurring detection, runway forecast, affordability, scam and anomaly scoring | Correct numbers and explainable risk scores |
| **P3** | Backend API & agent | FastAPI endpoints, LLM tool calling, confirmation flow, multilingual answers | A working agent that answers with real data and executes approved actions |
| **P4** | Frontend, product & pitch | UI, charts, chat interface, demo script, slides, backup video | A polished demo and a pitch that tells the story |

Suggested assignment: whoever is strongest in ML takes P2; whoever is strongest in UI takes P4; the exchange student at Creighton should present the pitch regardless of role, because the story is theirs.

### P1: Data & Nessie integration

**Responsibilities**

- Get API keys, verify the base URL and real field names, and document them for the team in the first hour.
- Check whether purchase dates include time of day, and whether credit card accounts support a limit field.
- Write a thin Nessie client (Python) with retries and error handling.
- Write the seed script following [Appendix A](#appendix-a-seed-data-spec): personas, three months of history, bills, deposits, and scam scenarios.
- Build the sync worker that polls Nessie and stores everything in SQLite, plus our own extra fields.
- Write `reset_demo.py`, which wipes and re-seeds the demo state in one command.
- Provide a static JSON export of the seed data early, so P2 and P3 can work before the database is ready.

**Done when:** running `seed.py` then `sync.py` produces a local database with consistent data for all personas, and `reset_demo.py` restores it in under a minute.

### P2: Engine (forecast & risk)

**Responsibilities**

- Recurring-transaction detection.
- Runway forecast, affordability check, and fix suggestions, following the spec in section 6.
- Scam check for transfers: score, reasons, and the questions to ask.
- Stretch: purchase anomaly detector (Isolation Forest first, autoencoder if time allows), plus an evaluation on injected fraud with detection and false-positive rates.
- Unit tests on the seed personas: the demo persona's runway date must be stable and believable.

**Works against:** P1's static JSON export until the database is ready.

**Done when:** pure Python functions such as `forecast(user_id, target_date)`, `can_afford(user_id, amount, date)`, and `check_transfer(user_id, payee_id, amount)` return correct, tested results that P3 can call.

### P3: Backend API & agent

**Responsibilities**

- FastAPI app exposing the endpoints in the contract below.
- Agent loop with tool calling. Tools: get accounts, get recent purchases, get bills, get forecast, check affordability, propose transfer, propose bill payment, explain a bill.
- System prompt with the persona context, strict rule to use only tool results for numbers, and answering in the user's language.
- Confirmation gate: proposed actions are stored with an ID and executed against Nessie only after `POST /actions/{id}/confirm`.
- Routes every transfer through P2's scam check before execution.

**Works against:** stub engine functions returning fixed values until P2 delivers.

**Done when:** the demo questions (in English and Spanish) get correct answers with real numbers, and an approved transfer shows up in Nessie.

### P4: Frontend, product & pitch

**Responsibilities**

- Decide web vs. Android in the first two hours. With four people and 24 hours, **web is the safer choice** unless someone is already fast with Kotlin.
- Screens, in priority order: dashboard with runway, chat with action approval cards, scam pause modal, bills, credit, alerts.
- The runway chart is the hero element: a line that ends before the flight date, turning safe after a fix is approved.
- Home-currency toggle.
- Demo script, slide deck (5–6 slides), Devpost write-up, and a recorded backup video of the full demo.

**Works against:** mock JSON responses matching the API contract until P3's backend is ready.

**Done when:** the full demo flow in section 9 runs smoothly end to end against the real backend.

### Shared contracts (agree on these in hours 0–2)

**Backend endpoints**

| Method | Endpoint | Returns |
|---|---|---|
| GET | `/api/users/{id}/summary` | Balances per account, runway date, target date, gap |
| GET | `/api/users/{id}/forecast?target=YYYY-MM-DD` | Daily projected balance series and upcoming events |
| GET | `/api/users/{id}/bills` | Bills with plain-language explanation and next date |
| GET | `/api/users/{id}/credit` | Balance, stored limit, utilization, suggested payment |
| POST | `/api/users/{id}/affordability` | New runway date and lowest buffer for a hypothetical expense |
| POST | `/api/chat` | Agent reply and, optionally, a proposed action |
| POST | `/api/actions/{id}/confirm` | Result of executing the action in Nessie |
| POST | `/api/transfers/check` | Risk score, reasons, and pause questions |
| GET | `/api/users/{id}/alerts` | Scam and anomaly alerts |

**Example payloads**

```json
// GET /api/users/ana/summary
{
  "accounts": [
    {"type": "Checking", "balance": 1840.25},
    {"type": "Savings", "balance": 2600.00},
    {"type": "Credit Card", "balance": 312.40, "limit": 500}
  ],
  "runway_date": "2027-04-18",
  "target_date": "2027-05-10",
  "gap": 410.00,
  "currency": "USD",
  "home_currency": "EUR",
  "fx_rate": 0.92
}
```

```json
// POST /api/chat  (response)
{
  "reply": "Sí, si gastas menos de 250 $. ...",
  "proposed_action": {
    "id": "act_123",
    "type": "transfer",
    "from": "savings",
    "to": "checking",
    "amount": 300,
    "effect": {"runway_date_after": "2027-05-14"}
  }
}
```

```json
// POST /api/transfers/check  (response)
{
  "risk_score": 87,
  "reasons": ["New payee", "43% of your checking balance", "Round amount"],
  "pause": true,
  "questions": [
    "Did someone contact you and ask you to pay urgently?",
    "Have you met or verified this person or company?"
  ]
}
```

### Repository structure

```
landed/
├── seed/            # P1: seed.py, reset_demo.py, personas.json
├── backend/
│   ├── nessie/      # P1: API client, sync worker, db models
│   ├── engine/      # P2: recurring.py, forecast.py, risk.py, tests/
│   ├── agent/       # P3: tools.py, prompts.py, loop.py
│   └── api/         # P3: FastAPI routes
├── frontend/        # P4
├── mocks/           # Shared mock JSON matching the contract
└── docs/            # P4: pitch deck, demo script, Devpost text
```

### Working agreements

- **One repo, short-lived branches,** merge to `main` often. `main` must always run.
- **Mocks first.** Nobody waits for anyone: P2 uses P1's JSON export, P3 uses stub engine functions, P4 uses the files in `mocks/`.
- **Keys in `.env`,** never committed.
- **Check-ins at each checkpoint** (15 minutes max): what works, what's blocked, what's cut.
- **Feature freeze** at the time set in the timeline. After that, only bug fixes and demo polish.
- **Sleep in shifts** if the event is 24h or longer, so there is always someone awake who can run the demo.

---

## 8. Timeline

Planned for a **24-hour** hackathon. For 36 hours, stretch the build and integration phases proportionally and move stretch goals earlier.

| Hours | Phase | P1 (Data) | P2 (Engine) | P3 (Agent/API) | P4 (Frontend/Pitch) |
|---|---|---|---|---|---|
| 0–2 | **Kickoff (all together)** | Keys, verify Nessie fields | Agree on forecast spec | Agree on API contract | Web vs. Android, wireframes, mocks |
| 2–8 | **Parallel build** | Nessie client, seed script, JSON export | Recurring detection, forecast v1 | FastAPI skeleton, agent with read tools | Dashboard, runway chart, chat UI on mocks |
| **8** | ✅ Checkpoint 1 | Seed data live in Nessie | Forecast correct on seed data | Agent answers read-only questions | UI skeleton navigable |
| 8–14 | **Integration** | Sync worker, SQLite cache, reset script | Affordability, fixes, scam check | Write actions with confirmation, scam check in transfer flow | Connect to real API, action cards, scam modal |
| **14** | ✅ Checkpoint 2 | | **Full demo path works end to end once** | | |
| 14–18 | **Stretch goals** | Extra personas, data polish | Anomaly detector and metrics | Spanish answers, bill explanations | Currency toggle, credit tab, bills tab |
| 18–20 | **Polish** | Demo reset tested | Edge cases, stable numbers | Prompt tuning, error handling | Visual polish, slides |
| **20** | 🧊 Feature freeze | | | | |
| 20–22 | **Stabilize** | Run reset + demo repeatedly | Fix bugs | Fix bugs | Record backup video |
| 22–24 | **Rehearse & submit** | Help rehearse | Prepare tech answers for Q&A | Prepare tech answers for Q&A | Devpost submission, final rehearsal |

### Scope tiers

| Tier | Includes | Status if we run out of time |
|---|---|---|
| **MVP (must have)** | Seed script, cache, recurring detection, runway forecast, agent with read tools + one write action (transfer), dashboard, chat, scam pause | The demo works |
| **Should have** | Affordability + fix suggestions, bill decoder, Spanish answers, home-currency toggle | The demo feels complete |
| **Stretch** | Credit tab, purchase anomaly detector with metrics, trusted contact, ATM finder | Nice extras |

---

## 9. Demo script

Target length: **2.5 minutes.** P4 drives the laptop; the presenter (ideally the Creighton exchange student) talks.

| Time | What's on screen | What the presenter says (gist) |
|---|---|---|
| 0:00–0:20 | Title slide | The problem: arriving in the US with money but no map of how banking works here. Personal story. |
| 0:20–0:45 | Dashboard for Ana, a student from Bilbao in Omaha | Balances in dollars and euros. The runway line ends on April 18, but her flight home is May 10. |
| 0:45–1:15 | Chat: "¿Puedo permitirme ir a Chicago este finde?" | The agent answers in Spanish with real numbers and warns that rent plus the trip leaves her short in two weeks. |
| 1:15–1:40 | Action card: move $300 from savings + weekly dining cap | She approves. The transfer goes through Nessie. The runway line now extends past her flight date. |
| 1:40–2:10 | She tries to send $800 to a new "landlord" | The scam pause appears with reasons and questions. She cancels. Money never left. |
| 2:10–2:30 | Architecture + endpoints slide | Seven Nessie resources, reads and writes. The LLM never calculates numbers. Built by an exchange student, for the next one. |

**Before going on stage:** run `reset_demo.py`, open all tabs, check the backup video plays, and turn off notifications.

---

## 10. Pitch outline

1. **Problem (30s).** International students face an unfamiliar financial system with irregular income and a hard deadline. Personal story from Creighton.
2. **Solution (15s).** Landed: a copilot that tells you if your money lasts, explains US banking in your language, and stops scams before money leaves.
3. **Demo (90s).** Section 9.
4. **How it works (20s).** Nessie endpoints used, deterministic forecast engine, LLM with tool calling and a confirmation gate, risk scoring on transfers.
5. **Impact and next steps (15s).** Who it helps, what we'd add with real data (real credit data, bank notifications, more languages).

**Q&A prep: questions to expect**

- *"How do you stop the LLM from hallucinating numbers?"* All numbers come from backend functions; the LLM only explains tool results.
- *"How accurate is the forecast?"* It is a transparent projection from recurring bills and recent spending, and the user can see every assumption.
- *"How did you validate the scam detection?"* On injected scenarios in synthetic data; we report it as such.
- *"What in the app is simulated?"* Credit limits, card freezes, exchange rates, and credit estimates.

---

## 11. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Nessie is slow or down during the demo | Demo fails | Local cache, reset script, backup video |
| Nessie field names or date formats differ from what we expect | Rework | P1 verifies everything in the first hour and documents it |
| Agent gives wrong numbers | Credibility lost | Numbers only from tools; test demo questions repeatedly |
| Agent answers vary between runs | Unreliable demo | Low temperature, rehearsed questions, fixed demo data |
| Integration fails late | Nothing works together | Contracts in hour 0–2, mocks, end-to-end checkpoint at hour 14 |
| Scope creep | Unfinished core | Scope tiers, feature freeze at hour 20 |
| Looks like "a chatbot wrapper" | Weak judging | Lead with the forecast and the scam pause, not the chat |

---

## Appendix A: Seed data spec

### Personas

| Persona | Profile | Purpose in demo |
|---|---|---|
| **Ana (main)** | Exchange student from Bilbao at Creighton, Omaha. Lump deposit from parents at the start of the semester, monthly rent, phone, insurance, gym, student credit card. | Runway forecast, agent, scam pause |
| **Raj** | Graduate student with a monthly stipend and part-time job deposits | Shows the forecast works with regular income too |
| **Lucía** | Student who is careful with money | Contrast: healthy runway, no alerts |

### History for Ana (about 3 months)

- **Deposits:** one large deposit from home at the start, one smaller top-up mid-semester.
- **Bills:** rent (monthly), phone (monthly), health insurance (monthly), gym (monthly), a streaming free trial that converts to paid soon.
- **Purchases around Omaha:** groceries, coffee, dining, transport, campus bookstore, with realistic amounts and slightly higher weekend spending. Merchants with real Omaha-area coordinates.
- **Credit card:** regular small purchases, utilization high enough (around 60%) to trigger the credit tip.
- **Calibration:** tune amounts so the runway date falls about three weeks before the flight home, and so moving $300 from savings fixes it.

### Scam and anomaly scenarios (triggered by a hidden demo button or script)

1. **Fake landlord.** Transfer of $800 to a brand-new payee with an urgent description.
2. **Impersonation scam.** Request to pay a "fine" to a new payee, round amount.
3. **Card testing (stretch).** Several $1–2 purchases at new online merchants, followed by a large electronics purchase.
4. **Impossible travel (stretch).** Two purchases far apart in a short time window (requires our own timestamps if Nessie dates are day-level).

---

## Appendix B: Team split if we build pure fraud detection

If the team prefers Idea A as the whole product, the same layered structure works:

| Person | Role | Owns |
|---|---|---|
| **P1** | Data & simulation | Seed script with normal behavior per persona, fraud injection with labels, sync worker, live "attack" simulator for the demo |
| **P2** | Detection models | Feature engineering, rules layer, Isolation Forest, autoencoder, evaluation metrics (detection rate vs. false positives) |
| **P3** | Backend & response flows | Scoring API, alert pipeline, "that was me / not me" feedback loop, simulated card freeze and refund, pre-transfer scam check, LLM explanations |
| **P4** | Frontend & pitch | "Your normal" map and fingerprint, alert screen, scam pause modal, trusted contact flow, demo and slides |

The demo for this version: show the persona's normal pattern, trigger a card-testing attack, show the explained alert and the "Not me" reversal, then stop a scam transfer before it leaves. Close with the metrics slide.