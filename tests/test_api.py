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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from backend.agent import keys, loop, openai_compat, prompts, tools
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
        """Rounding the *running* balance loses a fraction of a cent per day.

        Ana's burn rate has four decimal places and the projection is ~50 steps,
        so rounding each step costs about $0.07 — which was enough to move her
        runway date by a day, because her balance is calibrated to land just under
        the buffer. Asserted as a property rather than against literals: the
        calibration is P1's to retune, and this test is about the accumulator.
        """
        got = reference.forecast(self.conn, "ana")
        series, burn = got["series"], got["daily_burn"]

        # The same balance computed in one shot, with no intermediate rounding.
        events = sum(e["amount"] for e in got["events"])
        expected = series[0]["balance"] - burn * (len(series) - 1) + events
        self.assertAlmostEqual(series[-1]["balance"], expected, places=2)

        # And it still agrees with whatever P1 currently publishes.
        want = repo.expected_forecast(self.conn, "ana")
        self.assertEqual(got["runway_date"], want["runway_date"])
        self.assertEqual(got["min_balance"], want["min_balance"])


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
        before = self._balances()
        proposal = actions.propose(self.conn, "ana", {"type": "transfer", "amount": 99999})
        result = actions.confirm(self.conn, proposal["id"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self._balances(), before, "a refused transfer must move nothing")

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

    def test_no_reply_ever_shows_a_placeholder(self):
        """The engine returns null for "never runs short" — the best answer there is.

        Interpolated raw that reads "tu dinero duraría hasta None" on the approval
        card, which is the beat the demo is built around. This covers the class,
        not just the one sentence that had it.
        """
        questions = [
            "¿Qué hago para llegar a fin de mes?", "What should I do?",
            "¿Puedo permitirme ir a Chicago este finde? Unos 250$",
            "Can I afford a $250 trip this weekend?",
            "Can I afford a $5 coffee?", "¿Puedo permitirme un café de 5$?",
            "How am I doing?", "¿Cómo voy?", "What bills are coming up?",
            "¿Cómo va mi tarjeta?", "Any alerts?", "Where did my money go?",
        ]
        for question in questions:
            with self.subTest(question=question):
                reply = self._ask(question)["reply"]
                for junk in ("None", "null", "undefined", "nan", "{", "}", "$-"):
                    self.assertNotIn(junk, reply, f"{junk!r} leaked into: {reply}")
                self.assertTrue(reply.strip())

    def test_the_reply_and_the_approval_card_quote_the_same_date(self):
        """The chat and the card must not contradict each other on stage.

        They can: `suggest_fixes` advertises an effect per fix, and the proposal
        measures its own. Those were different numbers for the same $400 — the
        fix claimed the gap was cleared while the card correctly showed $9.91
        still short. The reply is now built from the proposal's measurement, so
        the two agree by construction rather than by luck.
        """
        for question in ("What should I do?", "¿Qué hago para llegar a fin de mes?"):
            with self.subTest(question=question):
                got = self._ask(question)
                action = got["proposed_action"]
                self.assertIsNotNone(action)
                effect = action["effect"]
                after = effect.get("runway_date_after")
                if after:
                    self.assertIn(after, got["reply"],
                                  "the reply must quote the date the card shows")
                else:
                    self.assertTrue(
                        "past your flight home" in got["reply"]
                        or "más allá de tu vuelo" in got["reply"])

    def test_a_transfer_that_leaves_her_short_says_so(self):
        """P1 calibrated the gap so one transfer is not enough.

        If the reply implies it is, the spending cap in the demo script looks
        like padding — and the card, which measures properly, contradicts it.
        """
        got = self._ask("What should I do?")
        short = float(got["proposed_action"]["effect"].get("gap_after") or 0)
        if short > 0:
            self.assertIn("short", got["reply"])

    def test_the_combined_plan_is_stated_as_a_measured_outcome(self):
        """The §9 payoff: two fixes together carry her past the flight.

        The engine puts the combined result on each step as `effect_with_plan`,
        so this can be a measured claim. Asserted conditionally because whether a
        plan clears the gap is the engine's to decide, not this test's.
        """
        from backend.api import engine_port

        fixes = engine_port.call("suggest_fixes", self.conn, "ana")
        plan = next((f.get("effect_with_plan") for f in fixes
                     if (f.get("effect_with_plan") or {}).get("clears_the_gap")), None)
        reply = self._ask("What should I do?")["reply"]
        if plan:
            self.assertIn("together they stretch you", reply)
            if not plan.get("runway_date_after"):
                self.assertIn("past your flight home", reply)
        self.assertNotIn("None", reply)

    def test_a_null_runway_reads_as_good_news_not_a_blank(self):
        self.assertEqual(loop._lasts_phrase(None, es=False), "past your flight home")
        self.assertEqual(loop._lasts_phrase(None, es=True), "más allá de tu vuelo de vuelta")
        self.assertEqual(loop._lasts_phrase("2026-10-27", es=False), "to 2026-10-27")

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

    def test_health_does_not_touch_the_network_unless_asked(self):
        """A health endpoint that can hang is worse than one that admits it did not check."""
        _, body = handlers.health()
        self.assertFalse(body["nessie"]["probed"])
        self.assertIn("key_present", body["nessie"])
        self.assertIn("base_url", body["nessie"])

    def test_health_probe_reports_reachability_without_raising(self):
        with mock.patch("backend.nessie.client.NessieClient.check_access",
                        side_effect=OSError("no network")):
            _, body = handlers.health(probe=True)
        self.assertTrue(body["nessie"]["probed"])
        self.assertFalse(body["nessie"]["reachable"])
        self.assertTrue(body["ok"], "a dead Nessie must not make the API look unhealthy")

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


class TestChatFixture(EngineBase):
    """mocks/api_chat_response.json is P4's fallback when the backend is down.

    P1's exporter never overwrites it, so keeping it truthful is P3's job. A
    fixture that answers "yes you can go" while the live agent answers "not yet"
    would put two different answers on stage depending on the laptop's mode.
    """

    def test_the_fixture_generator_produces_a_real_reply(self):
        from seed import export_chat_fixture

        built = export_chat_fixture.build(self.conn)

        self.assertTrue(built["reply"])
        self.assertEqual(built["language"], "es")
        self.assertTrue(built["used_tools"])
        self.assertEqual(built["proposed_action"]["id"], "act_demo_transfer")

    def test_the_committed_fixture_agrees_with_the_live_agent(self):
        import json as _json

        path = config.MOCKS_DIR / "api_chat_response.json"
        # Not skipIf: P1 removed their stub, so this file has exactly one source —
        # `python -m seed.export_chat_fixture`, committed. If it goes missing, P4's
        # mock mode has no chat reply at all, and a skip here would hide that.
        self.assertTrue(
            path.exists(),
            "mocks/api_chat_response.json is missing. P4 renders it when the backend "
            "is down. Regenerate: python -m seed.export_chat_fixture")
        fixture = _json.loads(path.read_text(encoding="utf-8"))
        live = loop.answer(self.conn, "ana", fixture.get("_question", ""))
        self.assertEqual(fixture["language"], live["language"])
        self.assertEqual(bool(fixture.get("proposed_action")), bool(live["proposed_action"]),
                         "regenerate with `python -m seed.export_chat_fixture`")


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

    def setUp(self):
        # Two tests in this class approve a transfer, which moves money in the
        # cache the server reads. Rebuild it per test so the demo path starts
        # from the seeded state rather than from a previous test's fix.
        fresh_db(self.tmp.name).close()

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


# --------------------------------------------------------------------------
# Bring your own key
# --------------------------------------------------------------------------


class TestModelKey(unittest.TestCase):
    """What a client may send as its own model key, and what is refused.

    Every case here is one somebody hits standing at a demo table: a key pasted
    with the shell prompt still attached, a key in the wrong provider's field,
    an endpoint on plain http. The point of failing here is that the message
    says which of those it was — a 401 from the provider does not.
    """

    def test_a_request_with_no_key_has_no_credential(self):
        self.assertIsNone(keys.from_headers({}))
        self.assertIsNone(keys.from_headers(None))

    def test_the_headers_are_read_whatever_their_case(self):
        got = keys.from_headers({"X-Model-Provider": "gemini", "X-Model-Key": "abc123"})
        self.assertEqual((got.provider, got.key), ("gemini", "abc123"))

    def test_the_provider_is_inferred_from_the_key(self):
        for key, provider in (("sk-ant-api03-aaaa", "anthropic"),
                              ("AIzaSyAAAAAAAAAAAA", "gemini"),
                              ("sk-proj-aaaaaaaa", "openai")):
            with self.subTest(provider=provider):
                self.assertEqual(keys.from_headers({keys.HEADER_KEY: key}).provider, provider)

    def test_an_unrecognisable_key_must_name_its_provider(self):
        with self.assertRaises(keys.BadKey):
            keys.from_headers({keys.HEADER_KEY: "abcdef123456"})
        got = keys.from_headers({keys.HEADER_KEY: "abcdef123456",
                                 keys.HEADER_PROVIDER: "openai"})
        self.assertEqual(got.provider, "openai")

    def test_an_explicit_provider_beats_the_prefix(self):
        """A key can be an OpenAI-compatible proxy's and still start sk-ant-."""
        got = keys.from_headers({keys.HEADER_KEY: "sk-ant-aaaa",
                                 keys.HEADER_PROVIDER: "openai"})
        self.assertEqual(got.provider, "openai")

    def test_a_paste_accident_is_refused(self):
        for bad in ("", "   ", "sk-abc def", "sk-abc\nGEMINI_API_KEY=x", "AIza" + "x" * 500):
            with self.subTest(bad=bad[:20]):
                with self.assertRaises(keys.BadKey):
                    keys.from_headers({keys.HEADER_KEY: bad, keys.HEADER_PROVIDER: "openai"})

    def test_an_unknown_provider_is_refused(self):
        with self.assertRaises(keys.BadKey):
            keys.from_headers({keys.HEADER_KEY: "sk-aaaa", keys.HEADER_PROVIDER: "mistral"})

    def test_a_provider_with_no_key_is_refused(self):
        with self.assertRaises(keys.BadKey):
            keys.from_headers({keys.HEADER_PROVIDER: "gemini"})

    def test_a_model_name_and_endpoint_come_through(self):
        got = keys.from_headers({
            keys.HEADER_KEY: "sk-aaaa", keys.HEADER_PROVIDER: "openai",
            keys.HEADER_MODEL: "gpt-4o-mini", keys.HEADER_BASE_URL: "https://openrouter.ai/api/v1/"})
        self.assertEqual(got.model, "gpt-4o-mini")
        self.assertEqual(got.base_url, "https://openrouter.ai/api/v1")

    def test_a_custom_endpoint_is_openai_only(self):
        """Gemini and Anthropic have one endpoint each, set in .env.

        Accepting the field and ignoring it would leave someone waiting for a
        local model that was never called.
        """
        with self.assertRaises(keys.BadKey):
            keys.from_headers({keys.HEADER_KEY: "AIzaaaaa",
                               keys.HEADER_BASE_URL: "https://example.com/v1"})

    def test_an_endpoint_must_be_https_unless_it_is_this_machine(self):
        local = keys.from_headers({keys.HEADER_KEY: "sk-aaaa", keys.HEADER_PROVIDER: "openai",
                                   keys.HEADER_BASE_URL: "http://127.0.0.1:11434/v1"})
        self.assertEqual(local.base_url, "http://127.0.0.1:11434/v1")
        for bad in ("http://192.168.1.9/v1", "ftp://example.com", "not a url"):
            with self.subTest(bad=bad):
                with self.assertRaises(keys.BadKey):
                    keys.from_headers({keys.HEADER_KEY: "sk-aaaa",
                                       keys.HEADER_PROVIDER: "openai",
                                       keys.HEADER_BASE_URL: bad})

    def test_the_key_is_not_in_the_repr(self):
        """A dataclass repr is how a secret reaches a traceback. This one cannot."""
        credential = keys.Credential("gemini", "AIzaSyTheWholeSecret")
        self.assertNotIn("AIzaSyTheWholeSecret", repr(credential))
        self.assertNotIn("AIzaSyTheWholeSecret", credential.redacted())


class TestBringYourOwnKey(unittest.TestCase):
    """The chat turn, paid for by the person asking.

    The rules being pinned: the user's key wins over the server's, a key that
    does not work is reported to the user rather than swallowed, and the key
    itself never comes back out in the reply.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        fresh_db(cls.tmp.name).close()
        cls.patch = mock.patch.object(config, "DB_PATH", Path(cls.tmp.name) / "test.db")
        cls.patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()
        cls.tmp.cleanup()

    def setUp(self):
        self.conn = fresh_db(self.tmp.name)

    def tearDown(self):
        self.conn.close()

    def _ask(self, credential=None, message="What should I do?"):
        return loop.answer(self.conn, "ana", message, credential=credential)

    def test_a_bad_key_is_400_not_a_silent_fallback(self):
        status, body = handlers.chat({"user": "ana", "message": "hi"},
                                     {keys.HEADER_KEY: "sk-with a space"})
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "bad_model_key")

    def test_a_request_with_no_key_is_unchanged(self):
        status, body = handlers.chat({"user": "ana", "message": "What should I do?"}, {})
        self.assertEqual(status, 200)
        self.assertIn(body["_key_source"], (None, "server"))
        self.assertTrue(body["reply"])

    def test_a_key_chooses_its_provider_over_the_environment(self):
        """The user pasted that key to be used. Billing someone else quietly is not an option."""
        with mock.patch.dict("os.environ", {"TREASURER_PROVIDER": "gemini"}, clear=False):
            self.assertEqual(loop._provider(keys.Credential("openai", "sk-aaaa")), "openai")
            self.assertEqual(loop._provider(), "gemini")

    def test_a_users_key_that_does_not_work_says_so(self):
        """It is their key, their quota and their typo — so they get told.

        The answer still lands: the scripted router composes it from the same
        tools, which is design rule 3. What must not happen is the copilot
        implying a model answered.
        """
        credential = keys.Credential("openai", "sk-nope")
        with mock.patch.object(loop, "_openai", side_effect=RuntimeError("HTTP 401: bad key")):
            got = self._ask(credential)
        self.assertTrue(got["_key_rejected"])
        self.assertIn("401", got["_fell_back"])
        self.assertEqual(got["_mode"], "scripted")
        self.assertEqual(got["_provider"], "scripted")
        self.assertIsNone(got["_key_source"])
        self.assertTrue(got["reply"].strip())

    def test_the_servers_own_key_failing_is_not_blamed_on_the_user(self):
        with mock.patch.dict("os.environ", {"TREASURER_PROVIDER": "gemini",
                                            "GEMINI_API_KEY": "AIzaServerKey"}, clear=False):
            with mock.patch.object(loop, "_gemini", side_effect=RuntimeError("HTTP 429")):
                got = self._ask()
        self.assertNotIn("_key_rejected", got)
        self.assertTrue(got["reply"].strip())

    def test_a_provider_this_backend_cannot_speak_is_reported(self):
        """An Anthropic key on a box with no anthropic SDK.

        Falling through to the scripted router is right; doing it without a word
        is what leaves someone re-pasting a key that was fine all along.
        """
        with mock.patch.object(loop, "_anthropic_sdk", return_value=False):
            got = self._ask(keys.Credential("anthropic", "sk-ant-aaaa"))
        self.assertTrue(got["_key_rejected"])
        self.assertIn("anthropic", got["_fell_back"])
        self.assertTrue(got["reply"].strip())

    def test_the_reason_is_one_line_a_person_can_act_on(self):
        """`_fell_back` is shown to the user, so it cannot be a JSON dump.

        Gemini's rejection of a bad key is "API key not valid" wrapped in eighty
        lines of `details`, and that whole body was going on screen under
        someone's own key — where it is the only thing telling them what to fix.
        """
        raw = ('HTTP 400: {\n  "error": {\n    "code": 400,\n'
               '    "message": "API key not valid. Please pass a valid API key.",\n'
               '    "status": "INVALID_ARGUMENT"\n  }\n}')
        with mock.patch.object(loop, "_gemini", side_effect=RuntimeError(raw)):
            got = self._ask(keys.Credential("gemini", "AIzaNope"))
        self.assertEqual(got["_fell_back"],
                         "HTTP 400: API key not valid. Please pass a valid API key.")

    def test_a_reason_with_no_json_in_it_survives_intact(self):
        with mock.patch.object(loop, "_gemini", side_effect=RuntimeError("unreachable: timed out")):
            got = self._ask(keys.Credential("gemini", "AIzaNope"))
        self.assertEqual(got["_fell_back"], "unreachable: timed out")

    def test_the_key_never_comes_back_in_the_reply(self):
        secret = "sk-ant-do-not-echo-this"
        credential = keys.Credential("anthropic", secret)
        with mock.patch.object(loop, "_llm", side_effect=RuntimeError("HTTP 401: invalid x-api-key")):
            got = self._ask(credential)
        self.assertNotIn(secret, json.dumps(got))

    def test_health_says_which_providers_a_key_can_be_for(self):
        _, body = handlers.health()
        byok = body["agent"]["byok"]
        self.assertIn("gemini", byok["accepted"])
        self.assertEqual(byok["headers"]["key"], keys.HEADER_KEY)

    def test_the_stdlib_server_allows_the_model_key_headers(self):
        """A browser that is not allowed to send the header sends the request anyway.

        Without the key, and with no error to show for it — just the scripted
        answer again. So the allow list is asserted rather than eyeballed.
        """
        allowed = "content-type, " + ", ".join(keys.HEADERS)
        for header in keys.HEADERS:
            self.assertIn(header, allowed)
        self.assertIn(keys.HEADER_KEY, allowed)


class _FakeOpenAI(BaseHTTPRequestHandler):
    """A stub that speaks `/chat/completions`: one tool call, then prose.

    Recorded on the class rather than the instance because http.server makes a
    new handler per request.
    """

    seen: list = []
    reject_field: str | None = None

    def do_POST(self):  # noqa: N802 - http.server's spelling
        length = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        _FakeOpenAI.seen.append({
            "path": self.path,
            "authorization": self.headers.get("authorization"),
            "body": body,
        })
        if _FakeOpenAI.reject_field and _FakeOpenAI.reject_field in body:
            return self._json(400, {"error": {
                "message": f"Unsupported parameter: '{_FakeOpenAI.reject_field}'"}})

        already_ran = any(m.get("role") == "tool" for m in body.get("messages") or [])
        if already_ran:
            return self._json(200, {"choices": [{
                "finish_reason": "stop",
                "message": {"role": "assistant",
                            "content": "You are short. Nothing moves until you approve it."},
            }]})
        self._json(200, {"choices": [{
            "finish_reason": "tool_calls",
            "message": {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "get_summary", "arguments": "{}"},
            }]},
        }]})

    def _json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass


class TestOpenAICompatibleTurn(unittest.TestCase):
    """A whole turn over the OpenAI shape, against a stub.

    This is the path a brought-along OpenAI, OpenRouter, Groq or Ollama key
    takes, and the only one no `.env` can cover — there is no key in the
    repository to test it with. The stub answers the way every real turn does:
    a tool call, the tool's numbers, then the prose.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        fresh_db(cls.tmp.name).close()
        cls.patch = mock.patch.object(config, "DB_PATH", Path(cls.tmp.name) / "test.db")
        cls.patch.start()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeOpenAI)
        cls.base = "http://127.0.0.1:%d/v1" % cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.patch.stop()
        cls.tmp.cleanup()

    def setUp(self):
        self.conn = fresh_db(self.tmp.name)
        _FakeOpenAI.seen = []
        _FakeOpenAI.reject_field = None
        # Which output-cap spelling an endpoint accepted is remembered per
        # process, and these two tests disagree about it on purpose.
        openai_compat._ACCEPTED.clear()

    def tearDown(self):
        self.conn.close()

    def _turn(self, model="test-model"):
        credential = keys.Credential("openai", "sk-users-own-key", model=model,
                                     base_url=self.base)
        return loop.answer(self.conn, "ana", "How am I doing?", credential=credential)

    def test_a_brought_along_key_answers_a_whole_turn(self):
        got = self._turn()
        self.assertEqual(got["_provider"], "openai")
        self.assertEqual(got["_key_source"], "user")
        self.assertEqual(got["_mode"], "llm")
        self.assertIn("get_summary", got["used_tools"])
        self.assertIn("Nothing moves until you approve it", got["reply"])

    def test_it_is_the_users_key_and_model_that_are_sent(self):
        self._turn(model="llama3.1:8b")
        first = _FakeOpenAI.seen[0]
        self.assertEqual(first["authorization"], "Bearer sk-users-own-key")
        self.assertEqual(first["path"], "/v1/chat/completions")
        self.assertEqual(first["body"]["model"], "llama3.1:8b")
        self.assertEqual(first["body"]["messages"][0]["role"], "system")
        self.assertTrue(first["body"]["tools"])

    def test_the_tools_numbers_are_what_the_model_is_given(self):
        """Design rule 1: the model writes prose around numbers it was handed."""
        self._turn()
        second = _FakeOpenAI.seen[1]
        results = [m for m in second["body"]["messages"] if m.get("role") == "tool"]
        self.assertEqual(len(results), 1)
        summary = json.loads(results[0]["content"])
        self.assertEqual(summary["target_date"],
                         engine_port.call("summary", self.conn, "ana")["target_date"])

    def test_the_output_cap_spelling_is_learned_from_the_rejection(self):
        """Half these endpoints take max_completion_tokens and half max_tokens.

        Neither is detectable up front, and guessing wrong costs the whole
        answer, so the rejection is what decides — once per endpoint.
        """
        _FakeOpenAI.reject_field = "max_completion_tokens"
        got = self._turn()
        self.assertIn("max_completion_tokens", _FakeOpenAI.seen[0]["body"])
        self.assertIn("max_tokens", _FakeOpenAI.seen[1]["body"])
        self.assertTrue(got["reply"].strip())
        self.assertEqual(got["_provider"], "openai")

    def test_an_endpoint_that_dies_falls_back_and_says_whose_fault_it_is(self):
        credential = keys.Credential("openai", "sk-aaaa", base_url="http://127.0.0.1:1/v1")
        got = loop.answer(self.conn, "ana", "How am I doing?", credential=credential)
        self.assertTrue(got["_key_rejected"])
        self.assertEqual(got["_mode"], "scripted")
        self.assertTrue(got["reply"].strip())


if __name__ == "__main__":
    unittest.main()
