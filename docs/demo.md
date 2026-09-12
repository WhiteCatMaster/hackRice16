# Demo runbook

About 2.5 minutes. One person drives, one presents. The original script and
pitch outline are in `begin.md` §9–§10; this is how to run it with what exists
today.

## Before going on stage

```bash
.venv/bin/python -m seed.reset_demo --arm                 # known state, scenarios fired
.venv/bin/uvicorn backend.api.app:app --port 8000         # Python 3.13
curl -s localhost:8000/api/health | python3 -m json.tool  # check the three things below
cd frontend && pnpm dev                                   # with TREASURER_API_BASE in .env.local
```

- [ ] `engine.engine_module` is `"backend.engine"`, not `null`.
- [ ] `agent.mode` is what you intend. `llm` needs quota: Gemini's free tier
  runs out after a handful of turns. `scripted` is reliable and gives the same
  numbers.
- [ ] The web top bar does **not** say RUNNING ON FIXTURES, unless you mean to
  demo on fixtures.
- [ ] Safety centre shows four alerts. If empty, re-run `--arm`.
- [ ] Decide which gap you will quote. Live mode says $425.90, fixtures say
  $409.91 ([why](engine.md#known-discrepancy-with-the-calibration)). Do not
  switch modes mid-demo.
- [ ] Backup video plays; notifications off; tabs already open.

**Approving an action really moves money in the cache.** Run
`seed.reset_demo --arm` between every rehearsal, or the runway will already be
fixed when you get on stage.

## Script (web)

| Time | On screen | What happens | Say |
|---|---|---|---|
| 0:00 | Title | — | Arriving in the US with money but no map of how banking works here |
| 0:20 | **Overview** for Ana, toggle `$` ↔ `€` | Balances in both currencies. The runway ends 2026-10-10; the flight home is 2026-10-31 | Her money runs out three weeks before her flight |
| 0:45 | **Runway** → *Your options* → *Can I afford it?* → `47.34` | "Not yet", with the plan that makes it a yes: cap dining at $12/week, move $400 from savings | Every number here is computed by the engine, not the model |
| 1:00 | **Copilot**: "¿Puedo permitirme ir a Chicago este finde? Unos 250$" | Answers in Spanish, shows the tools it used, proposes a transfer | The model picks tools and explains. It never does the maths, and it cannot move money |
| 1:15 | **Approve** on the action card | Dashboard re-reads: balance and runway date move | Only a tap moves money. `executed_in_nessie` says whether it reached the bank |
| 1:40 | **Safety** → *Send money* → the fake landlord | Paused: score 84, six reasons, three questions | International students are targeted by exactly this. We stop it before the money leaves |
| 2:00 | Same list → **Marta Aguirre** (roommate) | Goes through | A check that stops everything is not a feature |
| 2:10 | Architecture | — | Seven Nessie resource types, reads and writes. Deterministic engine, model behind a confirmation gate |

On the phone the flow is the same: **Overview**, **Runway**, **Ask** (the
copilot tab), **Safety**. After approving, every tab reloads and the app returns
to Overview.

## If something breaks

| Problem | Do |
|---|---|
| Model rate-limited mid-demo | Nothing. The reply still arrives from the scripted router with the same numbers |
| Backend dies | Unset `TREASURER_API_BASE` and restart `pnpm dev`: fixture mode. The chat and the approval still render, and say nothing was written |
| Numbers look wrong | Check `as_of` in the payload; then `reset_demo --arm` |
| Everything | Play the backup video |

## Q&A

- **How do you stop the model making up numbers?** It has no way to compute
  them. Every figure comes from a tool result, `used_tools` is on every reply,
  and the prompt forbids quoting anything else. The scripted mode proves the
  numbers exist without a model at all.
- **Can the AI move money?** No. It can only stage an action; `actions.py`
  executes it after the user approves. A test asks the agent to move $500 and
  asserts no balance changed.
- **How accurate is the forecast?** It is a transparent projection: scheduled
  bills plus the median of 30 days of spending. Every assumption is in the
  payload (`burn_profile`, `events`).
- **How did you validate scam detection?** On injected scenarios in synthetic
  data: 5/5 outcomes, 8/8 fraud purchases flagged, 0/480 normal purchases
  flagged. That is our own labelled data, not real-world evidence.
- **What is simulated?** Credit limits, APR, utilization, card freezes, exchange
  rates, spending caps and intra-day timestamps. Nessie has no such fields.
- **What happens if Nessie is down?** Nothing visible. Every read is from the
  local cache.
- **Whose API key?** The copilot runs on the server's key, or on the user's own
  pasted key (kept only on their device). With none, the scripted router.
