"""P3 regression tests: the API, the confirmation gate and the agent.

Run: python -m unittest discover tests -v

These run against whichever engine is live. Where a number is P1's published
calibration the test pins it exactly; everywhere else it pins the *invariant*
the demo depends on, so P2 can keep changing the engine without breaking P3.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from backend.agent import loop, prompts, tools
from backend.api import actions, engine_port, handlers, reference, serve
from backend.nessie import config, db, repo
from backend.nessie.sync import load_local
from seed.generator import build
from seed.scenarios import inject

AS_OF = date(2026, 9, 11)
PERSONAS = ("ana", "raj", "lucia")


def fresh_db(tmp: str):
    """A cache loaded from a freshly generated dataset, isolated per test class."""
    conn = db.connect(Path(tmp) / "test.db")
    load_local(build(as_of=AS_OF), conn)
    return conn


class EngineBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.conn = fresh_db(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        cls.tmp.cleanup()


# --------------------------------------------------------------------------


class TestReferenceMatchesCalibration(EngineBase):
    """P3's reference projection must reproduce P1's published numbers exactly.

    P1's handoff says: "If your engine disagrees with these, one of us has a bug."
    This is P3 taking that bet on the fallback it ships.
    """

    def test_every_persona_matches(self):
        for user in PERSONAS:
            want = repo.expected_forecast(self.conn, user)
            got = reference.forecast(self.conn, user)
            for field in ("runway_date", "gap", "min_balance", "min_balance_date"):
                with self.subTest(user=user, field=field):
                    self.assertEqual(got[field], want[field])

    def test_future_events_match(self):
        for user in PERSONAS:
            want = {(e["date"], e["amount"]) for e in repo.expected_forecast(self.conn, user)["future_events"]}
            got = {(e["date"], e["amount"]) for e in reference.forecast(self.conn, user)["events"]}
            self.assertEqual(got, want, user)

    def test_rounding_does_not_drift(self):
        """The bug that moves Ana's runway by a day: rounding the running balance.

        Each daily step loses a fraction of a cent; over 51 days that is enough to
        keep her above the buffer on 2026-10-10 and report the 11th instead.
        """
        got = reference.forecast(self.conn, "ana")
        self.assertEqual(got["runway_date"], "2026-10-10")
        self.assertEqual(got["min_balance"], -309.99)


class TestDemoInvariants(EngineBase):
    """The story in begin.md §9, asserted against whichever engine is live."""

    def test_ana_runs_out_before_her_flight(self):
        got = engine_port.call("summary", self.conn, "ana")
        self.assertIsNotNone(got["runway_date"])
        self.assertLess(got["runway_date"], got["target_date"])
        self.assertGreater(got["gap"], 0)

    def test_a_300_transfer_alone_does_not_close_the_gap(self):
        # The action card has two lines for a reason. If one transfer were enough,
        # the spending cap would look like padding.
        self.assertGreater(engine_port.call("summary", self.conn, "ana")["gap"], 300.0)

    def test_the_other_two_personas_are_healthy(self):
        for user in ("raj", "lucia"):
            with self.subTest(user=user):
                self.assertIsNone(engine_port.call("summary", self.conn, user)["runway_date"])

    def test_credit_utilization_triggers_the_tip(self):
        card = engine_port.call("credit", self.conn, "ana")
        self.assertGreater(card["utilization"], 0.30)
        self.assertTrue(card["tip"])


class TestContractShapes(EngineBase):
    """Every response must carry the keys frontend/lib/contract.ts declares."""

    def test_summary(self):
        got = engine_port.call("summary", self.conn, "ana")
        for key in ("user", "name", "accounts", "as_of", "runway_date", "target_date",
                    "gap", "safety_buffer", "daily_burn", "currency", "home_currency", "fx_rate"):
            self.assertIn(key, got)
        for account in got["accounts"]:
            self.assertIn(account["type"], ("Checking", "Savings", "Credit Card"))
            self.assertIsInstance(account["balance"], float)

    def test_forecast(self):
        got = engine_port.call("forecast", self.conn, "ana")
        for key in ("user", "target", "runway_date", "gap", "min_balance",
                    "min_balance_date", "daily_burn", "series", "events"):
            self.assertIn(key, got)
        self.assertTrue(got["series"])
        first = got["series"][0]
        self.assertEqual(set(first), {"date", "balance", "events"})
        for event in got["events"]:
            self.assertEqual(set(event) >= {"date", "amount", "label"}, True)

    def test_series_events_are_objects_not_numbers(self):
        """contract.ts wins over P1's fixture here — P4 renders {date, amount, label}."""
        got = engine_port.call("forecast", self.conn, "ana")
        with_events = [p for p in got["series"] if p["events"]]
        self.assertTrue(with_events)
        for event in with_events[0]["events"]:
            self.assertIsInstance(event, dict)
            self.assertIn("label", event)

    def test_bills_credit_alerts_activity_profile(self):
        bills = engine_port.call("bills", self.conn, "ana")
        self.assertTrue(bills["bills"])
        for bill in bills["bills"]:
            for key in ("id", "nickname", "payee", "amount", "next_date",
                        "recurring_day", "category", "explanation"):
                self.assertIn(key, bill)

        credit = engine_port.call("credit", self.conn, "ana")
        for key in ("balance", "limit", "utilization", "suggested_payment", "tip"):
            self.assertIn(key, credit)

        self.assertIn("alerts", engine_port.call("alerts", self.conn, "ana"))

        items = engine_port.call("activity", self.conn, "ana", limit=5)["items"]
        self.assertLessEqual(len(items), 5)
        for item in items:
            self.assertIn(item["kind"], ("purchase", "deposit", "withdrawal", "transfer"))
            if item["kind"] in ("purchase", "withdrawal", "transfer"):
                self.assertLess(item["amount"], 0, "money out must be negative")

        profile = engine_port.call("profile", self.conn, "ana")
        self.assertEqual(profile["home_city"], "Bilbao, Spain")
        self.assertEqual(profile["flight_home_date"], "2026-10-31")

    def test_activity_is_newest_first(self):
        items = engine_port.call("activity", self.conn, "ana", limit=10)["items"]
        stamps = [i["occurred_at"] for i in items]
        self.assertEqual(stamps, sorted(stamps, reverse=True))


class TestRisk(EngineBase):
    """The scam pause, and the false-positive control that matters just as much."""

    def _check(self, key):
        scenario = next(s for s in repo.scenarios(self.conn) if s["key"] == key)
        return engine_port.call(
            "check_transfer", self.conn, scenario["persona"],
            payee_id=scenario["payee_local_id"], amount=scenario["amount"],
            description=scenario.get("description"))

    def test_fake_landlord_pauses(self):
        got = self._check("fake_landlord")
        self.assertTrue(got["pause"])
        self.assertTrue(got["questions"])
        self.assertTrue(any("never" in r.lower() for r in got["reasons"]))

    def test_immigration_fine_pauses(self):
        self.assertTrue(self._check("immigration_fine")["pause"])

    def test_legit_roommate_does_not_pause(self):
        # A risk engine that stops everything is not a feature, and a judge will ask.
        got = self._check("legit_roommate")
        self.assertFalse(got["pause"])
        self.assertEqual(got["questions"], [])

    def test_risk_score_is_bounded(self):
        for key in ("fake_landlord", "immigration_fine", "legit_roommate"):
            score = self._check(key)["risk_score"]
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)

    def test_a_fired_scenario_shows_up_as_an_alert(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = fresh_db(tmp)
            self.assertEqual(engine_port.call("alerts", conn, "ana")["alerts"], [])
            inject("fake_landlord", conn, push=False)
            found = engine_port.call("alerts", conn, "ana")["alerts"]
            self.assertTrue(found, "firing a scenario must raise an alert")
            conn.close()


class TestConfirmationGate(EngineBase):
    """begin.md design rule 2: propose, approve, only then write."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = fresh_db(self.tmp.name)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _balances(self):
        person = repo.resolve_customer(self.conn, "ana")
        return {
            kind: repo.account_of_type(self.conn, person["id"], kind)["balance"]
            for kind in ("Checking", "Savings")
        }

    def test_proposing_moves_no_money(self):
        before = self._balances()
        actions.propose(self.conn, "ana", {"type": "transfer", "amount": 300})
        self.assertEqual(self._balances(), before)

    def test_confirming_moves_money(self):
        before = self._balances()
        proposal = actions.propose(self.conn, "ana", {"type": "transfer", "amount": 300})
        result = actions.confirm(self.conn, proposal["id"])
        self.assertEqual(result["status"], "executed")
        after = self._balances()
        self.assertAlmostEqual(after["Checking"], before["Checking"] + 300, places=2)
        self.assertAlmostEqual(after["Savings"], before["Savings"] - 300, places=2)

    def test_transfer_extends_the_runway(self):
        before = engine_port.call("summary", self.conn, "ana")["runway_date"]
        proposal = actions.propose(self.conn, "ana", {"type": "transfer", "amount": 400})
        actions.confirm(self.conn, proposal["id"])
        after = engine_port.call("summary", self.conn, "ana")["runway_date"]
        self.assertTrue(after is None or after > before,
                        f"the approved fix must push the runway out, got {after}")

    def test_effect_is_measured_or_honestly_blank(self):
        """Never echo an unchanged date back as if the action did nothing."""
        effect = actions.propose(self.conn, "ana", {"type": "transfer", "amount": 400})["effect"]
        if effect.get("measured"):
            self.assertNotEqual(effect["runway_date_after"], effect["runway_date_before"])
        else:
            self.assertIsNone(effect["runway_date_after"])
            self.assertIn("measured_note", effect)

    def test_never_claims_a_nessie_write_without_a_key(self):
        # Design rule 4. The UI prints this flag, so it must not flatter us.
        with mock.patch.object(config, "NESSIE_API_KEY", ""):
            proposal = actions.propose(self.conn, "ana", {"type": "transfer", "amount": 50})
            self.assertFalse(actions.confirm(self.conn, proposal["id"])["executed_in_nessie"])

    def test_overdrawing_savings_is_refused(self):
        proposal = actions.propose(self.conn, "ana", {"type": "transfer", "amount": 99999})
        result = actions.confirm(self.conn, proposal["id"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self._balances()["Savings"], 2600.0)

    def test_unknown_action_id_fails_politely(self):
        result = actions.confirm(self.conn, "act_nope")
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["executed_in_nessie"])

    def test_double_confirm_does_not_move_money_twice(self):
        proposal = actions.propose(self.conn, "ana", {"type": "transfer", "amount": 100})
        actions.confirm(self.conn, proposal["id"])
        mid = self._balances()
        actions.confirm(self.conn, proposal["id"])
        self.assertEqual(self._balances(), mid)

    def test_unsupported_action_is_rejected_at_propose(self):
        with self.assertRaises(ValueError):
            actions.propose(self.conn, "ana", {"type": "buy_bitcoin", "amount": 10})


class TestAgent(EngineBase):
    """The scripted router. No API key, no network, real numbers."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = fresh_db(self.tmp.name)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _ask(self, message, **kw):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            return loop.answer(self.conn, "ana", message, **kw)

    def test_affordability_question_quotes_engine_numbers(self):
        summary = engine_port.call("summary", self.conn, "ana")
        got = self._ask("¿Puedo permitirme ir a Chicago este finde? Unos 250$")
        self.assertIn("check_affordability", got["used_tools"])
        self.assertIn(summary["target_date"], got["reply"])

    def test_affordability_question_proposes_a_fix(self):
        got = self._ask("Can I afford a $250 trip this weekend?")
        self.assertIsNotNone(got["proposed_action"])
        self.assertEqual(got["proposed_action"]["type"], "transfer")

    def test_it_answers_in_the_language_it_was_asked_in(self):
        self.assertEqual(self._ask("¿Cómo va mi tarjeta?")["language"], "es")
        self.assertEqual(self._ask("How is my credit card doing?")["language"], "en")

    def test_language_can_be_forced(self):
        self.assertEqual(self._ask("How am I doing?", language="es")["language"], "es")

    def test_every_reply_reports_the_tools_it_used(self):
        for question in ("How am I doing?", "What bills are coming up?",
                         "How is my credit card?", "Any alerts?"):
            with self.subTest(question=question):
                self.assertTrue(self._ask(question)["used_tools"])

    def test_the_agent_cannot_move_money(self):
        """Every tool is read-only or a proposal. None of them execute."""
        for name in [t["name"] for t in tools.SCHEMA]:
            self.assertTrue(name in tools.READ_ONLY or name.startswith("propose_"), name)

        before = repo.account_of_type(
            self.conn, repo.resolve_customer(self.conn, "ana")["id"], "Savings")["balance"]
        self._ask("Move $500 from savings to checking right now")
        after = repo.account_of_type(
            self.conn, repo.resolve_customer(self.conn, "ana")["id"], "Savings")["balance"]
        self.assertEqual(before, after, "chat alone must never move money")

    def test_system_prompt_carries_the_persona_and_the_rule(self):
        system = prompts.system(self.conn, "ana")
        self.assertIn("Ana", system)
        self.assertIn("Bilbao", system)
        self.assertIn("2026-10-31", system)
        self.assertIn("do not calculate", system.lower())

    def test_forecast_tool_does_not_ship_the_whole_series_to_the_model(self):
        self.assertNotIn("series", tools.run(self.conn, "ana", "get_forecast", {}))


class TestEnginePort(EngineBase):
    def test_every_capability_resolves(self):
        for name in engine_port.CAPABILITIES:
            with self.subTest(name=name):
                fn, owner = engine_port.resolve(name)
                self.assertTrue(callable(fn))
                self.assertIn(owner, ("backend.engine", "p3-reference"))

    def test_status_is_honest_about_who_answered(self):
        status = engine_port.status()
        self.assertEqual(set(status["capabilities"]), set(engine_port.CAPABILITIES))
        self.assertTrue(status["note"])

    def test_it_falls_back_when_the_engine_lacks_a_capability(self):
        with mock.patch.object(engine_port, "_p2", return_value=object()):
            self.assertEqual(engine_port.resolve("summary")[1], "p3-reference")

    def test_it_falls_back_when_the_engine_will_not_import(self):
        with mock.patch.object(engine_port, "_p2", return_value=None):
            self.assertEqual(engine_port.resolve("forecast")[1], "p3-reference")
            self.assertTrue(engine_port.call("summary", self.conn, "ana")["accounts"])

    def test_unknown_kwargs_are_dropped_not_raised(self):
        got = engine_port.call("summary", self.conn, "ana", nonsense_kwarg=1)
        self.assertIn("accounts", got)

    def test_accepts_reports_the_extra_events_hook(self):
        self.assertIsInstance(engine_port.accepts("forecast", "extra_events"), bool)
        with mock.patch.object(engine_port, "_p2", return_value=None):
            self.assertTrue(engine_port.accepts("forecast", "extra_events"))


class TestHandlers(unittest.TestCase):
    """The route handlers, which know nothing about a web framework."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "test.db"
        fresh_db(cls.tmp.name).close()
        cls.patch = mock.patch.object(config, "DB_PATH", cls.path)
        cls.patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()
        cls.tmp.cleanup()

    def test_reads_return_200(self):
        for call in (lambda: handlers.summary("ana"), lambda: handlers.forecast("ana"),
                     lambda: handlers.bills("ana"), lambda: handlers.credit("ana"),
                     lambda: handlers.alerts("ana"), lambda: handlers.activity("ana", 5),
                     lambda: handlers.profile("ana"), lambda: handlers.fixes("ana")):
            status, body = call()
            self.assertEqual(status, 200)
            self.assertIsInstance(body, dict)

    def test_unknown_user_is_404_not_a_crash(self):
        for call in (lambda: handlers.summary("nobody"), lambda: handlers.bills("nobody"),
                     lambda: handlers.chat({"user": "nobody", "message": "hi"})):
            status, body = call()
            self.assertEqual(status, 404)
            self.assertEqual(body["error"], "unknown_user")

    def test_health_reports_both_layers(self):
        status, body = handlers.health()
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertIn("engine", body)
        self.assertIn("agent", body)
        self.assertIn(body["agent"]["mode"], ("llm", "scripted"))
        self.assertIn("ana", body["personas"])

    def test_bad_input_is_400_not_500(self):
        self.assertEqual(handlers.affordability("ana", {"amount": "lots"})[0], 400)
        self.assertEqual(handlers.affordability("ana", {})[0], 400)
        self.assertEqual(handlers.chat({"user": "ana", "message": "  "})[0], 400)

    def test_transfers_check_by_scenario_key(self):
        status, body = handlers.transfers_check({"user": "ana", "scenario": "fake_landlord"})
        self.assertEqual(status, 200)
        self.assertTrue(body["pause"])
        self.assertEqual(body["scenario"], "fake_landlord")

    def test_transfers_check_rejects_an_unknown_scenario(self):
        self.assertEqual(handlers.transfers_check({"scenario": "nope"})[0], 404)

    def test_transfers_check_without_a_scenario(self):
        status, body = handlers.transfers_check(
            {"user": "ana", "amount": 800, "description": "URGENT pay today"})
        self.assertEqual(status, 200)
        self.assertIn("risk_score", body)

    def test_affordability_endpoint(self):
        status, body = handlers.affordability("ana", {"amount": 250})
        self.assertEqual(status, 200)
        self.assertIn("affordable", body)
        self.assertIn("runway_date_after", body)


class TestHttpRoutes(unittest.TestCase):
    """A real HTTP round trip through the stdlib server.

    This is the one that proves the backend still serves the contract on a laptop
    where `pip install` failed — same handlers, no FastAPI.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        fresh_db(cls.tmp.name).close()
        cls.patch = mock.patch.object(config, "DB_PATH", Path(cls.tmp.name) / "test.db")
        cls.patch.start()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.patch.stop()
        cls.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as response:
            return response.status, json.load(response)

    def post(self, path, body):
        request = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode(),
            headers={"content-type": "application/json"})
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)

    def test_every_route_p4_calls(self):
        for path in ("/api/health", "/api/users/ana/summary", "/api/users/ana/forecast",
                     "/api/users/ana/bills", "/api/users/ana/credit", "/api/users/ana/alerts",
                     "/api/users/ana/activity?limit=8", "/api/users/ana/profile"):
            with self.subTest(path=path):
                status, body = self.get(path)
                self.assertEqual(status, 200)
                self.assertIsInstance(body, dict)

    def test_forecast_honours_the_target_query(self):
        _, body = self.get("/api/users/ana/forecast?target=2026-10-20")
        self.assertEqual(body["target"], "2026-10-20")
        self.assertEqual(body["series"][-1]["date"], "2026-10-20")

    def test_chat_and_confirm_round_trip(self):
        _, reply = self.post("/api/chat", {"user": "ana", "message": "What should I do?"})
        self.assertTrue(reply["reply"])
        action = reply["proposed_action"]
        self.assertIsNotNone(action)

        _, result = self.post(f"/api/actions/{action['id']}/confirm",
                              {"user": "ana", "action": action})
        self.assertEqual(result["status"], "executed")
        self.assertIn("executed_in_nessie", result)
        self.assertIsInstance(result["executed_in_nessie"], bool)

    def test_unknown_route_is_404_json(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/api/nope")
        self.assertEqual(caught.exception.code, 404)

    def test_the_full_demo_path(self):
        """begin.md §9, over HTTP, in order."""
        _, summary = self.get("/api/users/ana/summary")
        self.assertLess(summary["runway_date"], summary["target_date"])

        _, reply = self.post("/api/chat", {
            "user": "ana", "message": "¿Puedo permitirme ir a Chicago este finde? Unos 250$"})
        self.assertEqual(reply["language"], "es")
        action = reply["proposed_action"]

        _, result = self.post(f"/api/actions/{action['id']}/confirm",
                              {"user": "ana", "action": action})
        self.assertEqual(result["status"], "executed")

        _, after = self.get("/api/users/ana/summary")
        self.assertTrue(
            after["runway_date"] is None or after["runway_date"] > summary["runway_date"],
            f"the approved fix must push the runway out, got {after['runway_date']}")
        self.assertLess(after["gap"], summary["gap"])

        _, risk = self.post("/api/transfers/check", {"user": "ana", "scenario": "fake_landlord"})
        self.assertTrue(risk["pause"])
        self.assertTrue(risk["reasons"])

        _, control = self.post("/api/transfers/check", {"user": "ana", "scenario": "legit_roommate"})
        self.assertFalse(control["pause"])


if __name__ == "__main__":
    unittest.main()
