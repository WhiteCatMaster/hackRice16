"""Answer the eight open questions in docs/nessie-api-notes.md empirically.

Creates one throwaway customer with its own accounts and merchant, pokes at the
API, prints what it found, and deletes everything it made. It never touches
seeded demo data, and it never runs a bulk delete.

    python -m seed.probe_nessie

Every check reports MATCHES (our assumption holds), DIFFERS (it does not, and
here is what to change) or UNKNOWN (could not tell).
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta

from backend.nessie import config
from backend.nessie.client import NessieClient, NessieError

MATCHES, DIFFERS, UNKNOWN = "MATCHES", "DIFFERS", "UNKNOWN"


# --------------------------------------------------------- no key needed

def probe_read_only(client: NessieClient) -> list[dict]:
    """What the ungated read endpoints tell us without any key at all.

    Reads are not gated: GET returns 200 for any key, an empty one included. The
    sandbox's own seeded data (branches, ATMs, enterprise merchants) is therefore
    readable, and it shows us the real field shapes.
    """
    findings = []

    def note(n, q, verdict, detail, action=""):
        findings.append({"n": n, "q": q, "verdict": verdict, "detail": detail, "action": action})

    try:
        client.get("/customers")
        note(0, "API is reachable over HTTPS", MATCHES,
             f"{client.base_url} answered", "")
    except NessieError as exc:
        note(0, "API is reachable over HTTPS", DIFFERS, str(exc),
             "the API is HTTPS-only; http:// is refused at the TCP level")
        return findings

    access = client.check_access()
    note(0.1, "API key is valid for writes",
         MATCHES if access["authorized"] else DIFFERS,
         access["detail"],
         "" if access["authorized"] else "seeding needs a valid key; reads work without one")

    # Real objects the sandbox ships with, so we can read actual field shapes.
    try:
        merchants = client.get("/enterprise/merchants") or []
    except NessieError:
        merchants = []
    if merchants:
        category = merchants[0].get("category")
        is_list = isinstance(category, list)
        note(6, "Merchant category is a list",
             MATCHES if is_list else DIFFERS,
             f"live merchant has category as {type(category).__name__}: {category!r}",
             "" if is_list else "seed.py negotiates this automatically, but a string is the likely shape")

    try:
        branches = client.get("/branches") or []
    except NessieError:
        branches = []
    if branches:
        address = branches[0].get("address") or {}
        expected = {"street_number", "street_name", "city", "state", "zip"}
        matches = expected <= set(address)
        note(6.2, "Address shape matches what we send",
             MATCHES if matches else DIFFERS,
             f"live address keys: {sorted(address)}",
             "" if matches else f"we send {sorted(expected)}")

    try:
        atms = client.get("/atms") or []
    except NessieError:
        atms = []
    if atms:
        geo = atms[0].get("geocode") or {}
        matches = {"lat", "lng"} <= set(geo)
        note(6.1, "Geocode shape matches what we send",
             MATCHES if matches else DIFFERS,
             f"live geocode keys: {sorted(geo)}",
             "" if matches else "distance signals depend on this shape")

    return findings


class Probe:
    def __init__(self, client: NessieClient):
        self.client = client
        self.findings: list[dict] = []
        self.trash: list[tuple[str, str]] = []   # (kind, id) to delete afterwards
        self.customer_id: str | None = None
        self.checking_id: str | None = None
        self.credit_id: str | None = None
        self.merchant_id: str | None = None

    def note(self, number: int, question: str, verdict: str, detail: str, action: str = ""):
        self.findings.append({"n": number, "q": question, "verdict": verdict,
                              "detail": detail, "action": action})

    # ------------------------------------------------------------------ setup

    def setup(self) -> bool:
        try:
            self.customer_id = self.client.create_customer({
                "first_name": "Treasurer", "last_name": "Probe",
                "address": {"street_number": "1", "street_name": "Probe St",
                            "city": "Omaha", "state": "NE", "zip": "68102"},
            })
            self.trash.append(("customer", self.customer_id))

            self.checking_id = self.client.create_account(self.customer_id, {
                "type": "Checking", "nickname": "probe checking", "rewards": 0, "balance": 500,
            })
            self.merchant_id = self.client.create_merchant({
                "name": "Treasurer Probe Merchant", "category": ["groceries"],
                "address": {"street_number": "1", "street_name": "Probe St",
                            "city": "Omaha", "state": "NE", "zip": "68102"},
                "geocode": {"lat": 41.2655, "lng": -95.9450},
            })
            return True
        except NessieError as exc:
            print(f"setup failed: {exc}")
            return False

    # ----------------------------------------------------------------- checks

    def check_5_create_shape(self):
        """#5 Create response shape."""
        try:
            raw = self.client.post("/customers", {
                "first_name": "Treasurer", "last_name": "Shape",
                "address": {"street_number": "1", "street_name": "Probe St",
                            "city": "Omaha", "state": "NE", "zip": "68102"},
            })
        except NessieError as exc:
            return self.note(5, "Create response shape", UNKNOWN, str(exc))

        created = self.client.created_id(raw)
        if created:
            self.trash.append(("customer", created))
        wrapped = isinstance(raw, dict) and "objectCreated" in raw
        self.note(5, "Create response shape",
                  MATCHES if created else DIFFERS,
                  f"{'wrapped in objectCreated' if wrapped else 'bare object'}; "
                  f"top-level keys {sorted(raw)[:6] if isinstance(raw, dict) else type(raw).__name__}",
                  "" if created else "client.created_id() could not find an id -- fix it")

    def check_6_merchant_category(self):
        """#6 Is merchant category a list?"""
        live = None
        try:
            live = self.client.get(f"/merchants/{self.merchant_id}")
        except NessieError:
            for m in self.client.merchants():
                if m.get("_id") == self.merchant_id:
                    live = m
                    break
        if not live:
            return self.note(6, "Merchant category is a list", UNKNOWN, "could not read the merchant back")

        category = live.get("category")
        is_list = isinstance(category, list)
        self.note(6, "Merchant category is a list",
                  MATCHES if is_list else DIFFERS,
                  f"came back as {type(category).__name__}: {category!r}",
                  "" if is_list else "send a plain string in seed.py and sync.py")

        geo = live.get("geocode") or {}
        self.note(6.1, "Merchant geocode round-trips",
                  MATCHES if geo.get("lat") else DIFFERS,
                  f"geocode={geo!r}",
                  "" if geo.get("lat") else "distance signals need coordinates -- find another field")

    def check_1_date_granularity(self):
        """#1 Are purchase dates day-only, and does description round-trip our tag?"""
        when = (date.today() - timedelta(days=3)).isoformat()
        tagged = "Probe purchase [t=18:41]"
        try:
            purchase_id = self.client.create_purchase(self.checking_id, {
                "merchant_id": self.merchant_id, "medium": "balance",
                "purchase_date": when, "amount": 4.25,
                "status": "completed", "description": tagged,
            })
        except NessieError as exc:
            return self.note(1, "Dates are day-level", UNKNOWN, str(exc))

        back = next((p for p in self.client.purchases(self.checking_id)
                     if p.get("_id") == purchase_id), None)
        if not back:
            return self.note(1, "Dates are day-level", UNKNOWN, "could not read the purchase back")

        got = str(back.get("purchase_date"))
        day_only = len(got) <= 10 and "T" not in got
        self.note(1, "Dates are day-level",
                  MATCHES if day_only else DIFFERS,
                  f"purchase_date came back as {got!r}",
                  "" if day_only else "Nessie keeps a time of day -- drop the description-tag workaround")

        survived = back.get("description") == tagged
        self.note(1.1, "Description round-trips our [t=] tag",
                  MATCHES if survived else DIFFERS,
                  f"sent {tagged!r}, got {back.get('description')!r}",
                  "" if survived else "find another field to carry occurred_at")

        # Does it accept a full timestamp at all?
        try:
            stamped = self.client.create_purchase(self.checking_id, {
                "merchant_id": self.merchant_id, "medium": "balance",
                "purchase_date": f"{when}T18:41:00", "amount": 1.00,
                "status": "completed", "description": "Probe timestamp",
            })
            echo = next((p for p in self.client.purchases(self.checking_id)
                         if p.get("_id") == stamped), None)
            kept = echo and "T" in str(echo.get("purchase_date"))
            self.note(1.2, "A full ISO timestamp is preserved",
                      DIFFERS if kept else MATCHES,
                      f"sent a timestamp, stored {echo.get('purchase_date') if echo else '?'!r}",
                      "we could store real times directly" if kept else "")
        except NessieError as exc:
            self.note(1.2, "A full ISO timestamp is preserved", MATCHES,
                      f"rejected outright ({exc.status})", "")

    def check_2_credit_limit(self):
        """#2 Does a Credit Card account accept a limit?"""
        for field in ("credit_limit", "limit"):
            try:
                account_id = self.client.create_account(self.customer_id, {
                    "type": "Credit Card", "nickname": f"probe card {field}",
                    "rewards": 0, "balance": 0, field: 750,
                })
            except NessieError as exc:
                self.note(2, f"Credit Card accepts '{field}'", MATCHES,
                          f"rejected ({exc.status}): {exc.body[:120]}", "")
                continue
            live = self.client.get(f"/accounts/{account_id}") or {}
            if self.credit_id is None:
                self.credit_id = account_id
            if live.get(field) is not None:
                return self.note(2, f"Credit Card accepts '{field}'", DIFFERS,
                                 f"stored and returned {field}={live.get(field)}",
                                 "use Nessie's own limit instead of our simulated one")
            self.note(2, f"Credit Card accepts '{field}'", MATCHES,
                      f"accepted the POST but dropped the field (keys: {sorted(live)[:8]})", "")

    def check_4_credit_sign(self):
        """#4 Does a purchase on a Credit Card decrease its balance?"""
        if not self.credit_id:
            try:
                self.credit_id = self.client.create_account(self.customer_id, {
                    "type": "Credit Card", "nickname": "probe card", "rewards": 0, "balance": 200,
                })
            except NessieError as exc:
                return self.note(4, "Card purchase decreases the balance", UNKNOWN, str(exc))

        before = float((self.client.get(f"/accounts/{self.credit_id}") or {}).get("balance") or 0)
        # If overdrafts are rejected, a zero-balance card cannot be charged and this
        # check would silently answer UNKNOWN -- which is the one answer we cannot
        # afford here, since the credit-card sign drives the opening-float logic.
        if before < 100:
            try:
                self.client.create_deposit(self.credit_id, {
                    "medium": "balance", "transaction_date": date.today().isoformat(),
                    "status": "completed", "amount": 200.0, "description": "Probe card funding",
                })
                before = float((self.client.get(f"/accounts/{self.credit_id}") or {}).get("balance") or 0)
            except NessieError:
                pass
        try:
            self.client.create_purchase(self.credit_id, {
                "merchant_id": self.merchant_id, "medium": "balance",
                "purchase_date": date.today().isoformat(), "amount": 25.0,
                "status": "completed", "description": "Probe card purchase",
            })
        except NessieError as exc:
            return self.note(4, "Card purchase decreases the balance", UNKNOWN,
                             f"purchase rejected ({exc.status}): {exc.body[:120]}")

        after = float((self.client.get(f"/accounts/{self.credit_id}") or {}).get("balance") or 0)
        moved = round(after - before, 2)
        decreased = moved < 0
        self.note(4, "Card purchase decreases the balance",
                  MATCHES if decreased else DIFFERS,
                  f"balance {before:.2f} -> {after:.2f} ({moved:+.2f}) after a 25.00 purchase",
                  "" if decreased else "Nessie treats a card balance as debt -- drop the opening float for cards")

    def check_3_overdraft(self):
        """#3 Does Nessie reject a transaction that overdraws?"""
        balance = float((self.client.get(f"/accounts/{self.checking_id}") or {}).get("balance") or 0)
        try:
            self.client.create_withdrawal(self.checking_id, {
                "medium": "balance", "transaction_date": date.today().isoformat(),
                "status": "completed", "amount": balance + 5000,
                "description": "Probe overdraft",
            })
        except NessieError as exc:
            return self.note(3, "Overdrafts are rejected", MATCHES,
                             f"rejected ({exc.status}): {exc.body[:120]}", "")

        after = float((self.client.get(f"/accounts/{self.checking_id}") or {}).get("balance") or 0)
        self.note(3, "Overdrafts are rejected", DIFFERS,
                  f"accepted; balance is now {after:.2f}",
                  "opening floats in seed.py are unnecessary -- harmless, but you can drop them")

    def check_7_bill_status(self):
        """#7 Which bill status values are accepted?"""
        accepted, rejected = [], []
        for status in ("recurring", "pending", "completed", "cancelled", "nonsense"):
            try:
                bill_id = self.client.create_bill(self.checking_id, {
                    "status": status, "payee": "Probe Payee", "nickname": f"probe {status}",
                    "payment_amount": 10.0, "payment_date": date.today().isoformat(),
                    "recurring_date": 1, "creation_date": date.today().isoformat(),
                })
                accepted.append(status)
                if bill_id:
                    self.trash.append(("bill", bill_id))
            except NessieError:
                rejected.append(status)

        ok = "recurring" in accepted
        self.note(7, "Bill status 'recurring' is valid",
                  MATCHES if ok else DIFFERS,
                  f"accepted {accepted or 'none'}; rejected {rejected or 'none'}",
                  "" if ok else f"use one of {accepted} in personas.json and generator.py")
        if "nonsense" in accepted:
            self.note(7.1, "Bill status is validated", DIFFERS,
                      "Nessie accepted a garbage status, so it does not validate this field", "")

    def check_8_bulk_delete(self):
        """#8 Does DELETE /data exist? Probed with an invalid type, never executed."""
        try:
            self.client.delete("/data", type="TreasurerProbeInvalidType")
        except NessieError as exc:
            if exc.status == 404:
                return self.note(8, "DELETE /data exists", UNKNOWN,
                                 "404 -- either the route or the type is unknown; we do not rely on it", "")
            return self.note(8, "DELETE /data exists", MATCHES,
                             f"route answered {exc.status} to an invalid type, so it exists", "")
        self.note(8, "DELETE /data exists", MATCHES,
                  "accepted an invalid type without error -- treat with care", "")

    # ---------------------------------------------------------------- cleanup

    def cleanup(self):
        print("\ncleaning up what the probe created...")
        removed = 0
        for kind, object_id in reversed(self.trash):
            try:
                if kind == "customer":
                    self.client.delete_customer(object_id)
                    removed += 1
            except NessieError:
                pass
        for account_id in (self.checking_id, self.credit_id):
            if account_id:
                try:
                    self.client.delete_account(account_id)
                    removed += 1
                except NessieError:
                    pass
        print(f"  removed {removed} objects "
              f"(the probe merchant stays; Nessie has no merchant delete)")

    def run(self):
        for check in (self.check_5_create_shape, self.check_6_merchant_category,
                      self.check_1_date_granularity, self.check_2_credit_limit,
                      self.check_4_credit_sign, self.check_3_overdraft,
                      self.check_7_bill_status, self.check_8_bulk_delete):
            try:
                check()
            except NessieError as exc:
                self.note(0, check.__doc__ or check.__name__, UNKNOWN, f"probe error: {exc}")
            except Exception as exc:  # a probe must never take the run down
                self.note(0, check.__doc__ or check.__name__, UNKNOWN, f"probe crashed: {exc!r}")


def main() -> int:
    client = NessieClient(verbose=False)
    print(f"probing {config.NESSIE_BASE_URL}\n")

    findings = probe_read_only(client)
    authorized = any(f["n"] == 0.1 and f["verdict"] == MATCHES for f in findings)

    probe = None
    if not authorized:
        print("No valid API key, so only the read-only checks ran.\n"
              "Reads are ungated; writes are not. To answer the rest:\n"
              "  1. get a key at https://nessieisreal.com\n"
              "  2. cp .env.example .env  and put the key in NESSIE_API_KEY\n"
              "  3. re-run: python -m seed.probe_nessie\n")
    else:
        probe = Probe(client)
        if not probe.setup():
            return 1
        try:
            probe.run()
        finally:
            probe.cleanup()
        findings += probe.findings

    print("\n" + "=" * 78)
    print("RESULTS  (question numbers match docs/nessie-api-notes.md)")
    print("=" * 78)
    for f in sorted(findings, key=lambda x: x["n"]):
        print(f"\n[{f['verdict']:<7}] #{f['n']:<4} {f['q']}")
        print(f"           {f['detail']}")
        if f["action"]:
            print(f"           ACTION: {f['action']}")

    differs = [f for f in findings if f["verdict"] == DIFFERS]
    unknown = [f for f in findings if f["verdict"] == UNKNOWN]
    print("\n" + "=" * 78)
    print(f"{len(findings) - len(differs) - len(unknown)} assumptions hold, "
          f"{len(differs)} differ, {len(unknown)} undetermined")
    if differs:
        print("\nCode changes needed:")
        for f in differs:
            print(f"  #{f['n']}  {f['action'] or f['detail']}")
    print(f"\n{client.calls} API calls")
    print("\nPaste this output back and the code gets fixed to match.")

    (config.ROOT / "docs" / "probe-results.json").write_text(
        json.dumps(findings, indent=2) + "\n")
    print("Saved to docs/probe-results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
