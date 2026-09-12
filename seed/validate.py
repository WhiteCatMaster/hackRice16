"""Consistency checks on the generated dataset.

Every stated balance has to be reproducible from the transactions behind it. If a
judge adds up Ana's purchases and gets a different number than her dashboard, the
demo is over -- so this runs as part of seed and reset.
"""
from __future__ import annotations

from datetime import date, timedelta

from seed.generator import Dataset, haversine_km

TOLERANCE = 0.02


class Check:
    def __init__(self):
        self.results: list[tuple[bool, str]] = []

    def add(self, ok: bool, message: str):
        self.results.append((bool(ok), message))

    def ok(self) -> bool:
        return all(ok for ok, _ in self.results)

    def report(self) -> str:
        lines = [("  PASS  " if ok else "  FAIL  ") + msg for ok, msg in self.results]
        passed = sum(1 for ok, _ in self.results if ok)
        lines.append(f"\n{passed}/{len(self.results)} checks passed")
        return "\n".join(lines)


def validate(ds: Dataset) -> Check:
    check = Check()
    accounts = {a["local_id"]: a for a in ds.accounts}
    merchants = {m["local_id"]: m for m in ds.merchants}

    for account_id, account in accounts.items():
        if not account_id.startswith("acc_") or account.get("balance") in (None, 0.0):
            continue

        inflow = sum(d["amount"] for d in ds.deposits if d["account_local_id"] == account_id)
        inflow += sum(t["amount"] for t in ds.transfers if t["payee_local_id"] == account_id)
        outflow = sum(w["amount"] for w in ds.withdrawals if w["account_local_id"] == account_id)
        outflow += sum(t["amount"] for t in ds.transfers if t["payer_local_id"] == account_id)
        purchases = sum(p["amount"] for p in ds.purchases if p["account_local_id"] == account_id)

        if account["type"] == "Credit Card":
            # A card balance is debt: purchases minus what was paid off from checking.
            paid = sum(
                w["amount"] for w in ds.withdrawals
                if w.get("category") == "credit_card"
                and w["account_local_id"] == account_id.replace("_cc", "_chk")
            )
            expected = purchases - paid
        else:
            expected = inflow - outflow - purchases

        delta = abs(expected - account["balance"])
        check.add(
            delta <= TOLERANCE,
            f"{account['nickname']}: stated {account['balance']:.2f} vs "
            f"transactions {expected:.2f} (delta {delta:.2f})",
        )

    # Recent burn rate must be recoverable from the purchase history, because the
    # engine derives it that way.
    for key, cal in ds.calibration.items():
        checking = f"acc_{key}_chk"
        window_start = ds.as_of - timedelta(days=29)
        totals: dict[str, float] = {}
        for p in ds.purchases:
            if p["account_local_id"] != checking:
                continue
            if date.fromisoformat(p["purchase_date"]) >= window_start:
                totals[p["purchase_date"]] = totals.get(p["purchase_date"], 0.0) + p["amount"]
        daily = sorted(totals.get((window_start + timedelta(days=i)).isoformat(), 0.0) for i in range(30))
        median = (daily[14] + daily[15]) / 2
        target = cal["daily_discretionary"]
        check.add(
            abs(median - target) <= max(0.5, target * 0.05),
            f"{key}: median daily spend {median:.2f} matches calibrated burn {target:.2f}",
        )

    # The scam signals are only true if these never happened before.
    reserved = {m["local_id"] for m in ds.merchants if m.get("risk_tag")}
    used = {p["merchant_local_id"] for p in ds.purchases}
    check.add(
        not (reserved & used),
        f"scenario-only merchants stay out of history ({', '.join(sorted(reserved & used)) or 'clean'})",
    )

    scam_payees = {
        s["payee_local_id"] for s in ds.scenarios
        if s["kind"] == "transfer" and s.get("label") == "scam"
    }
    paid_before = {t["payee_local_id"] for t in ds.transfers}
    check.add(
        not (scam_payees & paid_before),
        "scam payees have never been paid before (the 'new payee' signal holds)",
    )

    control = [s for s in ds.scenarios if s.get("expect") == "allow"]
    check.add(
        bool(control) and all(s["payee_local_id"] in paid_before for s in control),
        "control scenario pays a payee with real history (false-positive check)",
    )

    # Ana carries the demo, so her headline numbers get pinned explicitly.
    ana = ds.calibration.get("ana")
    if ana:
        check.add(
            ana["runway_date"] == ana["runway_target"],
            f"ana runway {ana['runway_date']} hits target {ana['runway_target']}",
        )
        check.add(
            ana["runway_date"] and ana["runway_date"] < ana["flight_home"],
            f"ana runs out ({ana['runway_date']}) before her flight ({ana['flight_home']})",
        )
        check.add(
            300 < ana["gap"] < 700,
            f"ana's gap is {ana['gap']:.2f}: a single $300 transfer does not quite close it",
        )
        check.add(
            0.5 <= ana["credit_utilization"] <= 0.8,
            f"ana card utilization {ana['credit_utilization']:.1%} is high enough to trigger the tip",
        )

    # Impossible travel only reads as impossible if the geography says so.
    for scenario in ds.scenarios:
        if scenario["key"] != "impossible_travel":
            continue
        legs = scenario["purchases"]
        a, b = merchants[legs[0]["merchant_local_id"]], merchants[legs[-1]["merchant_local_id"]]
        km = haversine_km(a["lat"], a["lng"], b["lat"], b["lng"])
        minutes = (
            date.fromisoformat(legs[-1]["occurred_at"][:10]) == date.fromisoformat(legs[0]["occurred_at"][:10])
        ) and (int(legs[-1]["occurred_at"][11:13]) * 60 + int(legs[-1]["occurred_at"][14:16])
               - int(legs[0]["occurred_at"][11:13]) * 60 - int(legs[0]["occurred_at"][14:16]))
        check.add(
            km > 1000 and 0 < (minutes or 0) < 180,
            f"impossible travel: {km:.0f} km in {minutes} minutes",
        )

    return check


if __name__ == "__main__":
    import sys
    from seed.generator import build

    result = validate(build())
    print(result.report())
    sys.exit(0 if result.ok() else 1)
