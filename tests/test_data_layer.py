"""P1 regression tests. Run: python -m unittest discover tests -v"""
from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from backend.nessie import db, repo
from backend.nessie.sync import load_local, sync_from_nessie
from backend.nessie.timestamps import decode, encode
from seed.generator import build, haversine_km, measured_burn, project
from seed.scenarios import clear, inject
from seed.seed import push_dataset, reconcile_balances
from seed.validate import validate
from tests.fake_nessie import FakeNessie

AS_OF = date(2026, 9, 11)


class TestGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ds = build(as_of=AS_OF)

    def test_dataset_is_internally_consistent(self):
        result = validate(self.ds)
        self.assertTrue(result.ok(), "\n" + result.report())

    def test_generation_is_deterministic(self):
        again = build(as_of=AS_OF)
        self.assertEqual(
            [(p["local_id"], p["amount"]) for p in self.ds.purchases],
            [(p["local_id"], p["amount"]) for p in again.purchases],
        )

    def test_ana_runs_out_before_her_flight(self):
        ana = self.ds.calibration["ana"]
        self.assertIsNotNone(ana["runway_date"])
        self.assertLess(ana["runway_date"], ana["flight_home"])

    def test_a_300_transfer_alone_does_not_close_the_gap(self):
        # The demo needs two fixes, not one. If a single transfer were enough the
        # dining cap in the script would look like padding.
        self.assertGreater(self.ds.calibration["ana"]["gap"], 300.0)

    def test_moving_savings_plus_a_dining_cap_does_close_it(self):
        ana = self.ds.calibration["ana"]
        events = [(date.fromisoformat(e["date"]), e["amount"]) for e in ana["future_events"]]
        flight = date.fromisoformat(ana["flight_home"])
        capped = ana["daily_discretionary"] - 6.0
        fixed = project(ana["checking_balance"] + 300.0, AS_OF, flight, capped,
                        events, ana["safety_buffer"])
        self.assertIsNone(fixed.runway_date,
                          f"runway still breaks on {fixed.runway_date} after both fixes")

    def test_works_on_any_anchor_date(self):
        for offset in (0, 45, 111, 200):
            anchor = AS_OF + timedelta(days=offset)
            with self.subTest(anchor=anchor):
                result = validate(build(as_of=anchor))
                self.assertTrue(result.ok(), f"{anchor}\n" + result.report())

    def test_timestamps_survive_the_description_field(self):
        for original in ("Hy-Vee", "internet share", ""):
            encoded = encode(original, "2026-09-11T18:41")
            clean, when = decode(encoded, "2026-09-11")
            self.assertEqual(clean, original.strip())
            self.assertEqual(when, "2026-09-11T18:41")

    def test_purchases_carry_a_time_of_day(self):
        self.assertTrue(all("T" in p["occurred_at"] for p in self.ds.purchases))


class TestCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = db.connect(Path(self.tmp.name) / "test.db")
        db.init(self.conn)
        self.ds = build(as_of=AS_OF)
        load_local(self.ds, self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_snapshot_has_what_the_engine_needs(self):
        snap = repo.snapshot(self.conn, "ana")
        for key in ("accounts", "bills", "purchases", "daily_spend_30d", "credit"):
            self.assertIn(key, snap)
        self.assertEqual(len(snap["daily_spend_30d"]), 30)
        self.assertAlmostEqual(snap["credit"]["utilization"], 0.6248, places=3)

    def test_scam_payee_is_unknown_until_the_scenario_fires(self):
        self.assertIsNone(repo.known_payee(self.conn, "acc_ana_chk", "acc_cp_landlord"))
        self.assertIsNotNone(repo.known_payee(self.conn, "acc_ana_chk", "acc_p_marta"))

    def test_scenarios_inject_and_clear_cleanly(self):
        before = db.counts(self.conn)
        inject("card_testing", self.conn, verbose=False)
        inject("fake_landlord", self.conn, verbose=False)
        self.assertEqual(db.counts(self.conn)["purchases"], before["purchases"] + 6)
        clear(self.conn, verbose=False)
        self.assertEqual(db.counts(self.conn), before)

    def test_card_testing_burst_is_tight_enough_to_detect(self):
        inject("card_testing", self.conn, verbose=False)
        rows = [dict(r) for r in self.conn.execute(
            "SELECT * FROM purchases WHERE scenario='card_testing' ORDER BY occurred_at")]
        small = [r for r in rows if r["amount"] < 3]
        span = int(rows[-1]["occurred_at"][11:13]) * 60 + int(rows[-1]["occurred_at"][14:16]) \
            - int(rows[0]["occurred_at"][11:13]) * 60 - int(rows[0]["occurred_at"][14:16])
        self.assertGreaterEqual(len(small), 5)
        self.assertLess(span, 60)
        self.assertGreater(max(r["amount"] for r in rows), 500)

    def test_impossible_travel_is_geographically_impossible(self):
        inject("impossible_travel", self.conn, verbose=False)
        rows = [dict(r) for r in self.conn.execute(
            "SELECT p.*, m.lat, m.lng FROM purchases p JOIN merchants m ON m.id=p.merchant_id "
            "WHERE p.scenario='impossible_travel' ORDER BY p.occurred_at")]
        km = haversine_km(rows[0]["lat"], rows[0]["lng"], rows[-1]["lat"], rows[-1]["lng"])
        self.assertGreater(km, 1000)

    def test_expected_forecast_is_published_for_the_engine(self):
        expected = repo.expected_forecast(self.conn, "ana")
        self.assertEqual(expected["runway_date"], "2026-10-10")
        self.assertEqual(expected["runway_date"], expected["runway_target"])
        self.assertGreater(expected["gap"], 300.0)
        self.assertLess(expected["gap"], 700.0)


class TestNessieRoundTrip(unittest.TestCase):
    """Push everything to a fake Nessie and pull it back, which is the path we
    cannot rehearse against the live API without burning the sandbox."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = db.connect(Path(self.tmp.name) / "test.db")
        db.init(self.conn)
        self.ds = build(as_of=AS_OF)
        self.client = FakeNessie()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_push_then_sync_reproduces_the_dataset(self):
        pusher = push_dataset(self.ds, self.ds and self.client, self.conn, verbose=False)
        self.assertGreater(pusher.created, 500)

        report = reconcile_balances(self.ds, self.client, pusher, fix=True)
        self.assertTrue(report)

        counts = sync_from_nessie(self.conn, client=self.client, verbose=False)
        self.assertEqual(counts["purchases"], len(self.ds.purchases))
        self.assertEqual(counts["bills"], len(self.ds.bills))
        self.assertEqual(counts["deposits"], len(self.ds.deposits))
        self.assertEqual(counts["withdrawals"], len(self.ds.withdrawals))

    def test_chronological_order_never_overdraws(self):
        # FakeNessie rejects overdrafts the way the real sandbox does; if the
        # funding deposit went in after the spending this would raise.
        push_dataset(self.ds, self.client, self.conn, verbose=False)

    def test_local_only_fields_survive_the_round_trip(self):
        pusher = push_dataset(self.ds, self.client, self.conn, verbose=False)
        reconcile_balances(self.ds, self.client, pusher, fix=True)
        sync_from_nessie(self.conn, client=self.client, verbose=False)

        snap = repo.snapshot(self.conn, "ana")
        self.assertEqual(snap["customer"]["home_currency"], "EUR")
        self.assertAlmostEqual(snap["credit"]["limit"], 500.0)
        checking = next(a for a in snap["accounts"] if a["type"] == "Checking")
        self.assertAlmostEqual(checking["balance"], self.ds.calibration["ana"]["checking_balance"], places=2)

        # Intra-day times came back out of the description field, and the tag is gone.
        timed = [p for p in snap["purchases"] if p["occurred_at"]]
        self.assertGreater(len(timed), 100)
        self.assertFalse(any("[t=" in (p["description"] or "") for p in snap["purchases"]))

    def test_resume_does_not_duplicate(self):
        push_dataset(self.ds, self.client, self.conn, verbose=False)
        created_first = len(self.client.store["purchases"])
        again = push_dataset(self.ds, self.client, self.conn, resume=True, verbose=False)
        self.assertEqual(again.created, 0)
        self.assertEqual(len(self.client.store["purchases"]), created_first)


if __name__ == "__main__":
    unittest.main()


class TestAccessChecks(unittest.TestCase):
    """ping() used to pass with no key at all, because reads are ungated on this
    API. The first POST of a seed run then died with 401."""

    def test_a_valid_key_reads_as_authorized(self):
        client = FakeNessie()
        access = client.check_access()
        self.assertTrue(access["reachable"])
        self.assertTrue(access["authorized"], access["detail"])

    def test_no_key_is_not_authorized(self):
        client = FakeNessie()
        client.api_key = ""
        access = client.check_access()
        self.assertFalse(access["authorized"])
        self.assertIn("not set", access["detail"])

    def test_the_probe_creates_nothing(self):
        client = FakeNessie()
        before = len(client.store["customers"])
        client.check_access()
        self.assertEqual(len(client.store["customers"]), before)


class TestRunwayRobustness(unittest.TestCase):
    """The runway date is the demo's headline number, so every reasonable estimator
    has to agree on it.

    We originally calibrated Ana's balance to land one cent under the safety buffer.
    P2's engine measures the burn rate from the transactions rather than from the
    knob our solver found; seven cents over fifty days moved the date by a day and
    the dashboard disagreed with the fixtures. These tests exist so that cannot
    come back."""

    @classmethod
    def setUpClass(cls):
        cls.ds = build(as_of=AS_OF)

    def _project(self, cal, rate):
        events = [(date.fromisoformat(e["date"]), e["amount"]) for e in cal["future_events"]]
        flight = date.fromisoformat(cal["flight_home"])
        horizon = max(flight, date.fromisoformat(cal["runway_target"]))
        return project(cal["checking_balance"], AS_OF, horizon, rate,
                       events, cal["safety_buffer"])

    def test_published_rate_is_what_the_transactions_show(self):
        # Not the knob the solver found: a bank sees purchases, never the parameter
        # that generated them, so the published rate has to be the measurable one.
        for key, cal in self.ds.calibration.items():
            with self.subTest(persona=key):
                purchases = [p for p in self.ds.purchases
                             if p["account_local_id"] == f"acc_{key}_chk"]
                self.assertAlmostEqual(cal["daily_discretionary"],
                                       measured_burn(purchases, AS_OF), places=2)

    def test_runway_survives_an_estimator_being_wrong(self):
        cal = self.ds.calibration["ana"]
        for pct in (-12, -8, -5, -2, -1, 1, 2, 5, 8, 12):
            with self.subTest(error=f"{pct:+d}%"):
                moved = self._project(cal, round(cal["daily_discretionary"] * (1 + pct / 100), 4))
                self.assertEqual(str(moved.runway_date), cal["runway_date"],
                                 f"a {pct:+d}% error in the burn rate moved the runway date")

    def test_the_crossing_day_is_not_knife_edge(self):
        cal = self.ds.calibration["ana"]
        series = {p["date"]: p["balance"] for p in self._project(cal, cal["daily_discretionary"]).series}
        margin = cal["safety_buffer"] - series[cal["runway_target"]]
        self.assertGreater(margin, cal["daily_discretionary"],
                           "the balance lands less than a day's spend below the buffer")

    def test_the_crossing_is_never_knife_edge_at_any_anchor(self):
        """The invariant the fix actually provides.

        How much estimator error the date tolerates is `margin / days_to_target`,
        and the margin cannot exceed the crossing day's own drop without pushing the
        crossing earlier than the target. So the achievable tolerance depends on
        whether that day happens to carry a bill, and a flat percentage is not
        something the arithmetic can promise at every anchor.

        What it can promise is that the balance lands well inside the crossing day
        rather than on either edge, which is what "not knife-edge" means."""
        for offset in (0, 45, 111, 200):
            anchor = AS_OF + timedelta(days=offset)
            with self.subTest(anchor=anchor):
                ds = build(as_of=anchor)
                cal = ds.calibration["ana"]
                self.assertEqual(cal["runway_date"], cal["runway_target"])

                events = [(date.fromisoformat(e["date"]), e["amount"]) for e in cal["future_events"]]
                flight = date.fromisoformat(cal["flight_home"])
                horizon = max(flight, date.fromisoformat(cal["runway_target"]))
                series = {p["date"]: p["balance"] for p in project(
                    cal["checking_balance"], anchor, horizon,
                    cal["daily_discretionary"], events, cal["safety_buffer"]).series}

                target = date.fromisoformat(cal["runway_target"])
                on_target = series[cal["runway_target"]]
                day_before = series[(target - timedelta(days=1)).isoformat()]
                drop = day_before - on_target
                margin = cal["safety_buffer"] - on_target

                self.assertGreater(margin, 0, "balance is not below the buffer on the target day")
                self.assertGreater(margin, drop * 0.25,
                                   "lands too close to the bottom edge of the crossing day")
                self.assertLess(margin, drop * 0.75,
                                "lands too close to the top edge of the crossing day")
