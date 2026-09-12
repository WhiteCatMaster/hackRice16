"""The same API, on the standard library only.

P1 kept the whole data layer dependency-free so the demo could not be broken by a
failed `pip install`. This keeps that property for the API: if FastAPI is missing
or broken, `python -m backend.api.serve` serves the identical routes from
`http.server`. Same handlers, same JSON, same contract.
"""

from __future__ import annotations

import json
import logging
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from backend.api import handlers

log = logging.getLogger("landed.api")

#: (method, compiled path) -> handler taking (**path groups, query, body)
ROUTES = [
    ("GET", r"^/api/health$",
     lambda query, **kw: handlers.health(
         probe=(query.get("probe") or ["0"])[0] not in ("0", "false", ""))),
    ("GET", r"^/api/users/(?P<user>[^/]+)/summary$", lambda user, **kw: handlers.summary(user)),
    ("GET", r"^/api/users/(?P<user>[^/]+)/forecast$",
     lambda user, query, **kw: handlers.forecast(user, (query.get("target") or [None])[0])),
    ("GET", r"^/api/users/(?P<user>[^/]+)/bills$", lambda user, **kw: handlers.bills(user)),
    ("GET", r"^/api/users/(?P<user>[^/]+)/credit$", lambda user, **kw: handlers.credit(user)),
    ("GET", r"^/api/users/(?P<user>[^/]+)/alerts$", lambda user, **kw: handlers.alerts(user)),
    ("GET", r"^/api/users/(?P<user>[^/]+)/activity$",
     lambda user, query, **kw: handlers.activity(user, int((query.get("limit") or [8])[0]))),
    ("GET", r"^/api/users/(?P<user>[^/]+)/profile$", lambda user, **kw: handlers.profile(user)),
    ("GET", r"^/api/users/(?P<user>[^/]+)/fixes$", lambda user, **kw: handlers.fixes(user)),
    ("GET", r"^/api/scenarios$", lambda **kw: handlers.scenarios()),
    ("POST", r"^/api/users/(?P<user>[^/]+)/affordability$",
     lambda user, body, **kw: handlers.affordability(user, body)),
    ("POST", r"^/api/transfers/check$", lambda body, **kw: handlers.transfers_check(body)),
    ("POST", r"^/api/chat$", lambda body, **kw: handlers.chat(body)),
    ("POST", r"^/api/actions/propose$", lambda body, **kw: handlers.propose(body)),
    ("POST", r"^/api/actions/(?P<action_id>[^/]+)/confirm$",
     lambda action_id, body, **kw: handlers.confirm(action_id, body)),
]

COMPILED = [(method, re.compile(pattern), fn) for method, pattern, fn in ROUTES]


class Handler(BaseHTTPRequestHandler):
    server_version = "landed/1.0"

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        body = {}
        if method == "POST":
            length = int(self.headers.get("content-length") or 0)
            if length:
                try:
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    body = payload if isinstance(payload, dict) else {}
                except json.JSONDecodeError:
                    return self._send(400, {"error": "bad_json"})

        for route_method, pattern, fn in COMPILED:
            if route_method != method:
                continue
            match = pattern.match(parsed.path)
            if match:
                try:
                    status, payload = fn(**match.groupdict(), query=query, body=body)
                except Exception as exc:  # never 500 silently mid-demo
                    log.exception("handler failed")
                    status, payload = 500, {"error": "handler_failed", "message": str(exc)}
                return self._send(status, payload)

        self._send(404, {"error": "not_found", "path": parsed.path})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_OPTIONS(self):
        self._send(204, None)

    def _send(self, status: int, payload) -> None:
        data = b"" if payload is None else json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-headers", "content-type")
        self.send_header("access-control-allow-methods", "GET, POST, OPTIONS")
        self.end_headers()
        if data:
            self.wfile.write(data)

    def log_message(self, fmt, *args):
        log.info("%s", fmt % args)


def main(host: str = "127.0.0.1", port: int = 8000) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    log.info("Landed API (stdlib mode) on http://%s:%d", host, port)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    import sys
    main(port=int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
