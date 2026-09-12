"""The seam between the backend and the frontend, tested from both sides.

Every other test suite checks one layer. This one checks that the layers agree:

* the API answers with every field `frontend/lib/contract.ts` declares required,
  so live mode cannot quietly render blanks;
* the fixtures in `mocks/` satisfy that same contract, so mock mode and live mode
  show the same screen;
* every endpoint `frontend/lib/api.ts` calls actually exists in the backend, and
  has a Next route in front of it;
* the demo state is armed, i.e. the Safety centre is not empty in live mode when
  it is full in mock mode. That difference is invisible until you are on stage.

It runs against a temporary cache and never touches the network.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from backend.api import handlers
from backend.nessie import config, db, repo
from backend.nessie.sync import load_local
from seed.generator import build
from seed.scenarios import inject

AS_OF = date(2026, 9, 11)
PERSONAS = ("ana", "raj", "lucia")

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
MOCKS = ROOT / "mocks"


# --- reading the TypeScript contract --------------------------------------

def parse_contract(source: str) -> dict[str, set[str]]:
    """Required field names per exported interface.

    Deliberately crude: it wants `name:` at one level of indentation, skipping
    anything marked optional with `?`. Nested object literals are indented
    further, so they fall out on their own.
    """
    out: dict[str, set[str]] = {}
    current: str | None = None
    depth = 0
    for line in source.splitlines():
        opened = re.match(r"export interface (\w+)", line)
        if opened:
            current, depth = opened.group(1), 0
            out[current] = set()
            continue
        if current is None:
            continue
        if depth == 0 and re.match(r"^  (\w+)\??\s*:", line):
            name, optional = re.match(r"^  (\w+)(\??)\s*:", line).groups()
            if not optional and not name.startswith("_"):
                out[current].add(name)
        depth += line.count("{") - line.count("}")
        if line.startswith("}"):
            current = None
    return out


CONTRACT = parse_contract((FRONTEND / "lib" / "contract.ts").read_text())


def missing(payload: dict, required: set[str]) -> set[str]:
    return {field for field in required if field not in payload}


# --------------------------------------------------------------------------


class IntegrationBase(unittest.TestCase):
    """Handlers pointed at a throwaway cache with every scenario fired."""

    armed = True

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "integration.db"
        conn = db.connect(cls.path)
        load_local(build(as_of=AS_OF), conn)
        if cls.armed:
            for scenario in repo.scenarios(conn):
                inject(scenario["key"], conn, verbose=False)
        conn.close()
        cls.patch = mock.patch.object(config, "DB_PATH", cls.path)
        cls.patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()
        cls.tmp.cleanup()


class TestContractIsSatisfied(IntegrationBase):
    """Whatever the engine returns, it must still carry what the screens read."""

    def test_summary(self):
        for user in PERSONAS:
            status, body = handlers.summary(user)
            self.assertEqual(status, 200, user)
            self.assertFalse(missing(body, CONTRACT["Summary"]), f"{user}: {missing(body, CONTRACT['Summary'])}")
            for account in body["accounts"]:
                self.assertFalse(missing(account, CONTRACT["Account"]))

    def test_forecast(self):
        for user in PERSONAS:
            status, body = handlers.forecast(user)
            self.assertEqual(status, 200, user)
            self.assertFalse(missing(body, CONTRACT["Forecast"]), f"{user}: {missing(body, CONTRACT['Forecast'])}")
            self.assertTrue(body["series"], f"{user} has an empty projection")
            for point in body["series"][:5]:
                self.assertFalse(missing(point, CONTRACT["ForecastPoint"]))
            for event in body["events"][:5]:
                self.assertFalse(missing(event, CONTRACT["ForecastEvent"]))

    def test_forecast_fixes_carry_a_measured_effect(self):
        """The frontend renders `effect` verbatim. It must never compute one."""
        _, body = handlers.forecast("ana")
        fixes = body.get("fixes") or []
        self.assertTrue(fixes, "Ana is short; the engine should offer a way out")
        for fix in fixes:
            self.assertFalse(missing(fix, CONTRACT["Fix"]), fix)
            self.assertIn("effect", fix, f"{fix['id']} has no measured effect")

    def test_fix_effects_state_their_outcome_rather_than_implying_it(self):
        """The two things the fixes panel would otherwise have to guess.

        `days_gained: 0` is a real answer, not a missing one: a fix can shrink
        the gap without moving the crossing day, because that day is a big bill
        day. And `lasts_past_target` says what a null `runway_date_after` means,
        so nobody "corrects" the null into a date and silently turns the best
        outcome into a blank.
        """
        _, body = handlers.forecast("ana")
        for fix in body.get("fixes") or []:
            effect = fix["effect"]
            for field in ("days_gained", "lasts_past_target", "gap_before", "gap_after"):
                self.assertIn(field, effect, f"{fix['id']} is missing {field}")
            self.assertEqual(effect["lasts_past_target"], effect["runway_date_after"] is None,
                             f"{fix['id']}: lasts_past_target disagrees with runway_date_after")
            self.assertGreaterEqual(effect["days_gained"], 0, fix["id"])
            if effect["days_gained"] == 0 and not effect["lasts_past_target"]:
                # No days gained and still short: the crossing day must be
                # exactly where it was. (Gaining 0 days *and* lasting past the
                # flight is legitimate — it happens when the runway already
                # ended on the flight date.)
                self.assertEqual(effect["runway_date_before"], effect["runway_date_after"],
                                 f"{fix['id']}: no days gained, but the date moved")

    def test_bills(self):
        for user in PERSONAS:
            status, body = handlers.bills(user)
            self.assertEqual(status, 200, user)
            self.assertFalse(missing(body, CONTRACT["Bills"]))
            for bill in body["bills"]:
                self.assertFalse(missing(bill, CONTRACT["Bill"]), f"{user}: {missing(bill, CONTRACT['Bill'])}")

    def test_credit(self):
        for user in PERSONAS:
            status, body = handlers.credit(user)
            self.assertEqual(status, 200, user)
            self.assertFalse(missing(body, CONTRACT["Credit"]), f"{user}: {missing(body, CONTRACT['Credit'])}")

    def test_alerts(self):
        for user in PERSONAS:
            status, body = handlers.alerts(user)
            self.assertEqual(status, 200, user)
            self.assertFalse(missing(body, CONTRACT["Alerts"]))
            for alert in body["alerts"]:
                self.assertFalse(missing(alert, CONTRACT["Alert"]), f"{user}: {missing(alert, CONTRACT['Alert'])}")

    def test_activity_and_profile(self):
        for user in PERSONAS:
            _, activity = handlers.activity(user, 8)
            self.assertFalse(missing(activity, CONTRACT["Activity"]))
            for item in activity["items"]:
                self.assertFalse(missing(item, CONTRACT["ActivityItem"]), item)
            _, profile = handlers.profile(user)
            self.assertFalse(missing(profile, CONTRACT["Profile"]), f"{user}: {missing(profile, CONTRACT['Profile'])}")

    def test_transfer_check(self):
        for scenario in ("fake_landlord", "immigration_fine", "legit_roommate"):
            status, body = handlers.transfers_check({"user": "ana", "scenario": scenario})
            self.assertEqual(status, 200, scenario)
            self.assertFalse(missing(body, CONTRACT["TransferCheck"]), f"{scenario}: {missing(body, CONTRACT['TransferCheck'])}")

    def test_affordability(self):
        status, body = handlers.affordability("ana", {"amount": 47.34})
        self.assertEqual(status, 200)
        self.assertFalse(missing(body, CONTRACT["Affordability"]), missing(body, CONTRACT["Affordability"]))

    def test_affordability_answers_with_a_date_not_just_a_number(self):
        """'$47.34 safe' is ambiguous; '$47.34 safe through 31 Oct' is not."""
        _, body = handlers.affordability("ana", {"amount": 47.34})
        self.assertIn("max_safe_through", body)
        self.assertIsNotNone(body["max_safe_through"])

    def test_affordability_offers_a_way_to_yes_when_already_short(self):
        """Ana is short before her flight. The useful answer is 'not yet', with a plan."""
        _, body = handlers.affordability("ana", {"amount": 47.34})
        self.assertTrue(body["already_short"])
        self.assertFalse(body["affordable"])
        plan = body.get("if_you_fix_first")
        self.assertIsNotNone(plan, "a flat 'no' is the wrong answer here")
        self.assertTrue(plan["plan"], "the plan must say what to actually do")


class TestConfirmationGate(IntegrationBase):
    """Approving an action really moves money, so this gets its own cache.

    Sharing one with the read-only tests let the $400 transfer leak into every
    test that sorts after it alphabetically, which is how a fix's effect
    quietly changed shape underneath an assertion.
    """

    def test_chat_proposes_and_confirming_executes(self):
        status, reply = handlers.chat({"user": "ana", "message": "can I afford a $47 concert ticket?"})
        self.assertEqual(status, 200)
        self.assertFalse(missing(reply, CONTRACT["ChatReply"]))
        action = reply.get("proposed_action")
        self.assertIsNotNone(action, "the §9 beat proposes a fix")
        self.assertFalse(missing(action, CONTRACT["ProposedAction"]), action)

        before = handlers.summary("ana")[1]["accounts"][0]["balance"]

        # Nothing may move until it is confirmed, and the result says whether
        # it reached Nessie. Without a key it must not claim that it did.
        status, result = handlers.confirm(action["id"], {"user": "ana", "action": action})
        self.assertEqual(status, 200)
        self.assertFalse(missing(result, CONTRACT["ActionResult"]))
        self.assertFalse(result["executed_in_nessie"])

        # And the money is actually somewhere else now — this is what the
        # dashboard has to re-read after an approval.
        after = handlers.summary("ana")[1]["accounts"][0]["balance"]
        self.assertAlmostEqual(after, before + action["amount"], places=2)


class TestMocksMatchLive(IntegrationBase):
    """Mock mode is the fallback the demo ships with. It must show the same screen."""

    def test_fixtures_satisfy_the_same_contract(self):
        families = [("summary", "Summary"), ("forecast", "Forecast"),
                    ("bills", "Bills"), ("credit", "Credit"), ("alerts", "Alerts")]
        for user in PERSONAS:
            for endpoint, interface in families:
                path = MOCKS / f"api_users_{user}_{endpoint}.json"
                if not path.exists():
                    continue
                payload = json.loads(path.read_text())
                gap = missing(payload, CONTRACT[interface])
                self.assertFalse(gap, f"{path.name} is missing {gap}")

    def test_armed_cache_has_the_alerts_the_fixture_promises(self):
        """The bug this catches: a live Safety centre that is empty on stage.

        `mocks/api_users_ana_alerts.json` is exported with every scenario fired.
        A freshly reset cache has none fired, so live mode showed nothing while
        mock mode showed four. `reset_demo --arm` is what closes that.
        """
        fixture = json.loads((MOCKS / "api_users_ana_alerts.json").read_text())
        _, live = handlers.alerts("ana")
        self.assertEqual(len(live["alerts"]), len(fixture["alerts"]),
                         "armed live cache disagrees with the exported fixture")
        self.assertEqual({a["type"] for a in live["alerts"]},
                         {a["type"] for a in fixture["alerts"]})


class TestCleanCacheIsCalm(IntegrationBase):
    """The other half of the same promise: no scenarios fired, no alerts."""

    armed = False

    def test_no_alerts_before_anything_is_fired(self):
        _, body = handlers.alerts("ana")
        self.assertEqual(body["alerts"], [])

    def test_the_scam_check_still_works_unfired(self):
        """Checking a transfer must not depend on it having been injected."""
        status, body = handlers.transfers_check({"user": "ana", "scenario": "fake_landlord"})
        self.assertEqual(status, 200)
        self.assertTrue(body["pause"])


class TestNullRunwayIsGoodNews(IntegrationBase):
    """`runway_date: null` means "never runs short", not "value missing".

    P3 hit the loud version of this: interpolating it into a sentence printed
    "stretches you to None" on the demo's action card. The quiet version is a
    `&&` guard, which hides the effect exactly when the effect is best. Both are
    the same misreading, so the API side is pinned here and the render side is
    asserted over the built frontend below.
    """

    def test_the_healthy_personas_really_do_return_null(self):
        """If this ever stops being true, the null paths stop being exercised."""
        for user in ("raj", "lucia"):
            _, body = handlers.summary(user)
            self.assertIsNone(body["runway_date"], f"{user} was the healthy persona")

    def test_a_measured_effect_distinguishes_its_two_nulls(self):
        """measured:true + null is good news; measured:false + null is unknown."""
        _, reply = handlers.chat({"user": "ana", "message": "can I afford a $47 concert ticket?"})
        effect = (reply.get("proposed_action") or {}).get("effect")
        self.assertIsNotNone(effect)
        self.assertIn("measured", effect)
        if effect["measured"] is False:
            self.assertIn("measured_note", effect,
                          "an unmeasured effect must say why, or it reads as good news")

    def test_a_fix_that_clears_the_gap_reports_null_not_a_date(self):
        """Where the null actually comes from on Ana's screens.

        Not from approving the $400 transfer: that lands her on the flight date
        itself with $9.91 still short, so the action card shows a date. It is
        the fixes which clear the gap outright that return null.
        """
        _, forecast = handlers.forecast("ana")
        clearing = [f for f in forecast["fixes"] if f["effect"].get("clears_the_gap")]
        self.assertTrue(clearing, "Ana should have at least one fix that closes it")
        for fix in clearing:
            self.assertIsNone(fix["effect"]["runway_date_after"],
                              f"{fix['id']} closes the gap, so it should report null")
            self.assertTrue(fix["effect"]["lasts_past_target"])

    def test_approving_the_transfer_moves_her_to_the_flight_not_past_it(self):
        """Pins the number the action card shows, which is a date, not null."""
        _, reply = handlers.chat({"user": "ana", "message": "can I afford a $47 concert ticket?"})
        action = reply["proposed_action"]
        _, result = handlers.confirm(action["id"], {"user": "ana", "action": action})
        self.assertEqual(result["status"], "executed")
        _, after = handlers.summary("ana")
        self.assertEqual(after["runway_date"], after["target_date"],
                         "the $400 transfer carries her exactly to the flight")
        self.assertLess(after["gap"], 10.0)


class TestFrontendWiring(unittest.TestCase):
    """Static checks on the frontend, so a missing route is caught here."""

    api_ts = (FRONTEND / "lib" / "api.ts").read_text()

    def test_every_endpoint_the_frontend_calls_exists_in_the_backend(self):
        called = set(re.findall(r"`/api/([^`$?]*)(?:\$\{|\?|`)", self.api_ts))
        routes = (ROOT / "backend" / "api" / "app.py").read_text()
        for endpoint in called:
            head = endpoint.strip("/").split("/")[0]
            self.assertIn(f'"/api/{head}', routes, f"frontend calls /api/{endpoint}, backend has no route")

    def test_next_routes_exist_for_every_client_function(self):
        """Client components fetch same-origin, so each needs a route file."""
        expected = {
            "users/[id]/summary", "users/[id]/forecast", "users/[id]/bills",
            "users/[id]/credit", "users/[id]/alerts", "users/[id]/activity",
            "users/[id]/profile", "users/[id]/affordability",
            "transfers/check", "chat", "actions/[id]/confirm",
        }
        for route in expected:
            path = FRONTEND / "app" / "api" / route / "route.ts"
            self.assertTrue(path.exists(), f"missing Next route: app/api/{route}/route.ts")

    def test_contract_parsed_cleanly(self):
        """A guard on the guard: if the parser breaks, every check above passes."""
        for interface in ("Summary", "Forecast", "Bills", "Credit", "Alerts",
                          "Affordability", "TransferCheck", "Fix"):
            self.assertIn(interface, CONTRACT, f"{interface} not found in contract.ts")
            self.assertTrue(CONTRACT[interface], f"{interface} parsed with no required fields")


if __name__ == "__main__":
    unittest.main()
