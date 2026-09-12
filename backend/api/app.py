"""FastAPI app. The routes are exactly the ones P4 calls.

Every route is one line over `handlers.py`, which holds the actual logic and
knows nothing about FastAPI. `serve.py` serves the same handlers from the
standard library if this app cannot be imported.

    uvicorn backend.api.app:app --reload --port 8000
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api import handlers

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="ExchangeTreasurer API",
    version="1.0",
    description="P3: the backend API and agent for ExchangeTreasurer, a financial copilot for "
                "international students. Contract: begin.md §7.",
)

# P4 proxies server-side so this is not strictly needed, but it makes the API
# usable straight from a browser tab or a phone during the demo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


def _send(result) -> JSONResponse:
    status, body = result
    return JSONResponse(status_code=status, content=body)


async def _body(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


@app.get("/api/health")
def health(probe: bool = False):
    return _send(handlers.health(probe=probe))


@app.get("/api/users/{user}/summary")
def summary(user: str):
    return _send(handlers.summary(user))


@app.get("/api/users/{user}/forecast")
def forecast(user: str, target: str | None = None):
    return _send(handlers.forecast(user, target))


@app.get("/api/users/{user}/bills")
def bills(user: str):
    return _send(handlers.bills(user))


@app.get("/api/users/{user}/credit")
def credit(user: str):
    return _send(handlers.credit(user))


@app.get("/api/users/{user}/alerts")
def alerts(user: str):
    return _send(handlers.alerts(user))


@app.get("/api/users/{user}/activity")
def activity(user: str, limit: int = 8):
    return _send(handlers.activity(user, limit))


@app.get("/api/users/{user}/profile")
def profile(user: str):
    return _send(handlers.profile(user))


@app.get("/api/users/{user}/fixes")
def fixes(user: str):
    return _send(handlers.fixes(user))


@app.post("/api/users/{user}/affordability")
async def affordability(user: str, request: Request):
    return _send(handlers.affordability(user, await _body(request)))


@app.post("/api/transfers/check")
async def transfers_check(request: Request):
    return _send(handlers.transfers_check(await _body(request)))


@app.post("/api/chat")
async def chat(request: Request):
    return _send(handlers.chat(await _body(request)))


@app.post("/api/actions/propose")
async def propose(request: Request):
    return _send(handlers.propose(await _body(request)))


@app.post("/api/actions/{action_id}/confirm")
async def confirm(action_id: str, request: Request):
    return _send(handlers.confirm(action_id, await _body(request)))


@app.get("/api/scenarios")
def scenarios():
    return _send(handlers.scenarios())


def main() -> None:
    import uvicorn
    uvicorn.run("backend.api.app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
