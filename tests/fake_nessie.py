"""In-memory stand-in for the Nessie API.

P1's push and sync paths are the code most likely to break on stage and the code
we cannot exercise without a live key, so we exercise them against a double that
mimics Nessie's shapes: `_id` keys, the {code, message, objectCreated} create
envelope, day-precision dates, and balances the server computes itself.
"""
from __future__ import annotations

import re
from itertools import count

from backend.nessie.client import NessieClient, NessieError


class FakeNessie(NessieClient):
    def __init__(self, reject_overdraft: bool = True):
        super().__init__(api_key="fake", base_url="http://fake")
        self.ids = count(1)
        self.store: dict[str, dict] = {
            "customers": {}, "accounts": {}, "merchants": {}, "purchases": {},
            "bills": {}, "deposits": {}, "withdrawals": {}, "transfers": {},
        }
        self.reject_overdraft = reject_overdraft

    def _new_id(self) -> str:
        return f"{next(self.ids):024x}"

    def _created(self, collection: str, obj: dict) -> dict:
        obj["_id"] = self._new_id()
        self.store[collection][obj["_id"]] = obj
        return {"code": 201, "message": "Created", "objectCreated": obj}

    def _apply(self, account_id: str, delta: float):
        account = self.store["accounts"].get(account_id)
        if account is None:
            raise NessieError("POST", account_id, 404, "account not found")
        new_balance = round(account["balance"] + delta, 2)
        if self.reject_overdraft and new_balance < 0:
            raise NessieError("POST", account_id, 400, "insufficient funds")
        account["balance"] = new_balance

    def request(self, method: str, path: str, payload=None, params=None):
        self.calls += 1
        path = path.rstrip("/")

        if method == "GET":
            if path == "/customers":
                return list(self.store["customers"].values())
            if path == "/merchants":
                return list(self.store["merchants"].values())
            m = re.fullmatch(r"/customers/(\w+)/accounts", path)
            if m:
                return [a for a in self.store["accounts"].values() if a["customer_id"] == m.group(1)]
            m = re.fullmatch(r"/accounts/(\w+)", path)
            if m:
                return self.store["accounts"].get(m.group(1))
            m = re.fullmatch(r"/accounts/(\w+)/(purchases|bills|deposits|withdrawals|transfers)", path)
            if m:
                account_id, collection = m.group(1), m.group(2)
                if collection == "transfers":
                    return [t for t in self.store["transfers"].values()
                            if account_id in (t["payer_id"], t["payee_id"])]
                return [x for x in self.store[collection].values() if x["account_id"] == account_id]
            raise NessieError(method, path, 404, "no such route")

        if method == "POST":
            if path == "/customers":
                return self._created("customers", dict(payload))
            if path == "/merchants":
                return self._created("merchants", dict(payload))
            m = re.fullmatch(r"/customers/(\w+)/accounts", path)
            if m:
                obj = dict(payload, customer_id=m.group(1), balance=float(payload.get("balance") or 0))
                return self._created("accounts", obj)
            m = re.fullmatch(r"/accounts/(\w+)/(purchases|bills|deposits|withdrawals|transfers)", path)
            if m:
                account_id, collection = m.group(1), m.group(2)
                obj = dict(payload)
                if collection == "transfers":
                    obj["payer_id"] = account_id
                    self._apply(account_id, -float(obj["amount"]))
                    self._apply(obj["payee_id"], float(obj["amount"]))
                else:
                    obj["account_id"] = account_id
                    if collection == "deposits":
                        self._apply(account_id, float(obj["amount"]))
                    elif collection in ("withdrawals", "purchases"):
                        self._apply(account_id, -float(obj["amount"]))
                return self._created(collection, obj)
            raise NessieError(method, path, 404, "no such route")

        if method == "PUT":
            m = re.fullmatch(r"/accounts/(\w+)", path)
            if m:
                self.store["accounts"][m.group(1)].update(payload)
                return {"code": 202, "message": "Updated"}

        if method == "DELETE":
            m = re.fullmatch(r"/(customers|accounts)/(\w+)", path)
            if m:
                self.store[m.group(1)].pop(m.group(2), None)
                return {"code": 204}

        raise NessieError(method, path, 405, "not implemented in the fake")

    def ping(self):
        return True, "ok"
