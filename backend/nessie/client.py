"""Thin Nessie REST client.

stdlib only (urllib). Handles the two things that actually bite during a hackathon:
retries on flaky/slow responses, and surfacing the *server's* error body instead of
a bare "HTTP 400", because Nessie's field names are the #1 source of lost hours.
"""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import config


class NessieError(RuntimeError):
    def __init__(self, method: str, path: str, status: int | None, body: str):
        self.method, self.path, self.status, self.body = method, path, status, body
        super().__init__(f"{method} {path} -> {status}: {body[:500]}")


class NessieClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 20.0,
        max_retries: int = 4,
        verbose: bool = False,
    ):
        self.api_key = api_key if api_key is not None else config.NESSIE_API_KEY
        self.base_url = (base_url or config.NESSIE_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.verbose = verbose
        self.calls = 0

    # ---------------------------------------------------------------- transport

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        query = dict(params or {})
        query["key"] = self.api_key
        return f"{self.base_url}/{path.lstrip('/')}?{urllib.parse.urlencode(query)}"

    def request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        params: dict | None = None,
    ) -> Any:
        if not self.api_key:
            raise NessieError(method, path, None, "NESSIE_API_KEY is not set (see .env.example)")

        url = self._url(path, params)
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"

        last: Exception | None = None
        for attempt in range(self.max_retries):
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                self.calls += 1
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode() or "null"
                if self.verbose:
                    print(f"  {method} {path} -> {resp.status}")
                return json.loads(raw)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode(errors="replace")
                # 4xx means we sent something wrong; retrying won't help.
                if exc.code < 500 and exc.code != 429:
                    raise NessieError(method, path, exc.code, body) from exc
                last = NessieError(method, path, exc.code, body)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last = NessieError(method, path, None, repr(exc))

            if attempt < self.max_retries - 1:
                delay = (2**attempt) * 0.6 + random.random() * 0.3
                if self.verbose:
                    print(f"  retry {attempt + 1}/{self.max_retries - 1} in {delay:.1f}s ({last})")
                time.sleep(delay)

        raise last  # type: ignore[misc]

    def get(self, path, **params):
        return self.request("GET", path, params=params or None)

    def post(self, path, payload):
        return self.request("POST", path, payload=payload)

    def put(self, path, payload):
        return self.request("PUT", path, payload=payload)

    def delete(self, path, **params):
        return self.request("DELETE", path, params=params or None)

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def created_id(response: Any) -> str | None:
        """Nessie wraps creates as {code, message, objectCreated:{_id,...}}.

        Some deployments return the object directly, so handle both.
        """
        if not isinstance(response, dict):
            return None
        obj = response.get("objectCreated") or response
        if isinstance(obj, dict):
            return obj.get("_id") or obj.get("id")
        return None

    def ping(self) -> tuple[bool, str]:
        """Cheap reachability + key check. Never raises."""
        try:
            self.get("/customers")
            return True, "ok"
        except NessieError as exc:
            return False, str(exc)

    # ------------------------------------------------------------------- reads

    def customers(self) -> list[dict]:
        return self.get("/customers") or []

    def customer(self, customer_id: str) -> dict:
        return self.get(f"/customers/{customer_id}")

    def accounts(self) -> list[dict]:
        return self.get("/accounts") or []

    def customer_accounts(self, customer_id: str) -> list[dict]:
        return self.get(f"/customers/{customer_id}/accounts") or []

    def merchants(self) -> list[dict]:
        res = self.get("/merchants")
        # Some Nessie builds paginate merchants as {"data": [...]}
        if isinstance(res, dict):
            return res.get("data") or res.get("results") or []
        return res or []

    def purchases(self, account_id: str) -> list[dict]:
        return self.get(f"/accounts/{account_id}/purchases") or []

    def bills(self, account_id: str) -> list[dict]:
        return self.get(f"/accounts/{account_id}/bills") or []

    def deposits(self, account_id: str) -> list[dict]:
        return self.get(f"/accounts/{account_id}/deposits") or []

    def withdrawals(self, account_id: str) -> list[dict]:
        return self.get(f"/accounts/{account_id}/withdrawals") or []

    def transfers(self, account_id: str) -> list[dict]:
        return self.get(f"/accounts/{account_id}/transfers") or []

    def loans(self, account_id: str) -> list[dict]:
        return self.get(f"/accounts/{account_id}/loans") or []

    # ------------------------------------------------------------------ writes

    def create_customer(self, payload: dict) -> str:
        return self.created_id(self.post("/customers", payload))

    def create_account(self, customer_id: str, payload: dict) -> str:
        return self.created_id(self.post(f"/customers/{customer_id}/accounts", payload))

    def create_merchant(self, payload: dict) -> str:
        return self.created_id(self.post("/merchants", payload))

    def create_purchase(self, account_id: str, payload: dict) -> str:
        return self.created_id(self.post(f"/accounts/{account_id}/purchases", payload))

    def create_bill(self, account_id: str, payload: dict) -> str:
        return self.created_id(self.post(f"/accounts/{account_id}/bills", payload))

    def create_deposit(self, account_id: str, payload: dict) -> str:
        return self.created_id(self.post(f"/accounts/{account_id}/deposits", payload))

    def create_withdrawal(self, account_id: str, payload: dict) -> str:
        return self.created_id(self.post(f"/accounts/{account_id}/withdrawals", payload))

    def create_transfer(self, account_id: str, payload: dict) -> str:
        return self.created_id(self.post(f"/accounts/{account_id}/transfers", payload))

    def delete_customer(self, customer_id: str):
        return self.delete(f"/customers/{customer_id}")

    def delete_account(self, account_id: str):
        return self.delete(f"/accounts/{account_id}")
