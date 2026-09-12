# Landed

A financial copilot for international students in their first year in the US, with
built-in scam protection. Built on Capital One's Nessie mock banking API.

Full plan: [begin.md](begin.md). Team split, timeline, demo script and pitch live there.

## Status

| Layer | Owner | State |
|---|---|---|
| Data & Nessie integration | P1 | **done** — see [docs/data-layer.md](docs/data-layer.md) |
| Engine (forecast & risk) | P2 | not started |
| Backend API & agent | P3 | not started |
| Frontend & pitch | P4 | not started |

## Quick start

No dependencies for the data layer — Python 3.11+, standard library only.

```bash
cp .env.example .env          # add NESSIE_API_KEY when you have one
python -m seed.reset_demo     # generate, validate, cache, and write mocks/
python -m backend.nessie.repo # see what is in the cache
```

That works with no API key and no network. With a key:

```bash
python -m seed.seed --push    # push the dataset to Nessie, then cache it
```

Then:

- **P2** — start at `repo.snapshot(conn, "ana")` and `repo.expected_forecast(conn, "ana")`.
- **P3** — `mocks/api_*.json` fix every response shape in the contract.
- **P4** — same files, drop-in fixtures for every screen.

## Tests

```bash
python -m unittest discover tests
```

18 tests, including a full push-and-sync round trip against an in-memory Nessie.

## Before the demo

```bash
python -m seed.reset_demo && python -m seed.scenarios --clear
```
