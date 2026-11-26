"""API tests for Gift Exchange Forge (Flask test client)."""

import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402

TODAY = dt.date.today()
D = lambda n: (TODAY + dt.timedelta(days=n)).isoformat()  # noqa: E731

BRIEF = """[Exchange]
name: API Exchange
budget: 30
draw: {draw}
shopping: {shopping}
exchange: {exchange}
shipping: 3
circle: api-circle

[Participants]
Ada Lovelace | ada@example.com | House A
Alan Turing | alan@example.com | House A
Grace Hopper | grace@example.com | House B
Edsger Dijkstra | edsger@example.com | House B
""".format(draw=D(7), shopping=D(14), exchange=D(21))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app(os.path.join(self.tmp, "test.db"))
        self.client = self.app.test_client()
        self.exchange_id = self._create()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _create(self):
        res = self.client.post("/api/exchanges", json={"brief": BRIEF})
        self.assertEqual(res.status_code, 200)
        return res.get_json()["exchange"]["id"]

    def _get(self, path):
        res = self.client.get(path)
        self.assertEqual(res.status_code, 200)
        return res.get_json()

    # -- basics -----------------------------------------------------------
    def test_health(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["ok"])

    def test_index_page_is_served(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Gift Exchange Forge", res.get_data(as_text=True))

    def test_samples_are_listed(self):
        data = self._get("/api/samples")
        self.assertGreaterEqual(len(data["samples"]), 6)
        self.assertIn("brief", data["samples"][0])

    def test_sample_can_be_loaded(self):
        res = self.client.post("/api/samples/load", json={"sample": "family_christmas"})
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(len(payload["exchange"]["participants"]), 8)

    def test_unknown_sample_is_rejected(self):
        res = self.client.post("/api/samples/load", json={"sample": "nope"})
        self.assertEqual(res.status_code, 400)

    # -- exchanges --------------------------------------------------------
    def test_create_and_list(self):
        data = self._get("/api/exchanges")
        self.assertEqual(len(data["exchanges"]), 1)
        self.assertEqual(data["exchanges"][0]["name"], "API Exchange")
        self.assertEqual(data["exchanges"][0]["participants"], 4)

    def test_get_exchange_includes_report(self):
        data = self._get("/api/exchanges/" + self.exchange_id)
        self.assertIn("report", data)
        self.assertEqual(len(data["report"]["axes"]), 5)
        self.assertIn("score", data["report"])

    def test_missing_exchange_is_404(self):
        res = self.client.get("/api/exchanges/does-not-exist")
        self.assertEqual(res.status_code, 404)

    def test_update_settings(self):
        res = self.client.put(
            "/api/exchanges/" + self.exchange_id,
            json={"name": "Renamed", "budget": 45, "shipping_days": 6},
        )
        self.assertEqual(res.status_code, 200)
        ex = res.get_json()["exchange"]
        self.assertEqual(ex["name"], "Renamed")
        self.assertEqual(ex["budget"], 45)
        self.assertEqual(ex["shipping_days"], 6)

    def test_delete_exchange(self):
        res = self.client.delete("/api/exchanges/" + self.exchange_id)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.client.get("/api/exchanges").get_json()["exchanges"], [])

    # -- participants -----------------------------------------------------
    def test_add_participant_gets_an_access_code(self):
        res = self.client.post(
            "/api/exchanges/" + self.exchange_id + "/participants",
            json={"name": "Katherine Johnson", "email": "kj@example.com"},
        )
        self.assertEqual(res.status_code, 200)
        people = res.get_json()["exchange"]["participants"]
        self.assertEqual(len(people), 5)
        self.assertTrue(people[-1]["access_code"])

    def test_participant_without_name_is_rejected(self):
        res = self.client.post(
            "/api/exchanges/" + self.exchange_id + "/participants", json={"name": " "}
        )
        self.assertEqual(res.status_code, 400)

    def test_update_participant_wishes_and_purchase(self):
        res = self.client.patch(
            "/api/exchanges/" + self.exchange_id + "/participants/ada-lovelace",
            json={
                "wishes": [{"item": "Book", "price": 20, "note": "blue"}],
                "purchased": {"Book": 19.5},
            },
        )
        self.assertEqual(res.status_code, 200)
        people = res.get_json()["exchange"]["participants"]
        ada = [p for p in people if p["id"] == "ada-lovelace"][0]
        self.assertEqual(ada["wishes"][0]["item"], "Book")
        self.assertEqual(ada["purchased"]["Book"], 19.5)

    def test_delete_participant(self):
        res = self.client.delete(
            "/api/exchanges/" + self.exchange_id + "/participants/ada-lovelace"
        )
        self.assertEqual(res.status_code, 200)
        people = res.get_json()["exchange"]["participants"]
        self.assertEqual(len(people), 3)

    # -- exclusions -------------------------------------------------------
    def test_add_and_remove_exclusion(self):
        res = self.client.post(
            "/api/exchanges/" + self.exchange_id + "/exclude",
            json={"a": "Ada Lovelace", "b": "Grace Hopper"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.get_json()["exchange"]["exclusions"]), 1)
        res = self.client.delete(
            "/api/exchanges/" + self.exchange_id
            + "/exclude?a=ada-lovelace&b=grace-hopper"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.get_json()["exchange"]["exclusions"]), 0)

    def test_exclusion_needs_two_known_people(self):
        res = self.client.post(
            "/api/exchanges/" + self.exchange_id + "/exclude",
            json={"a": "Ada Lovelace", "b": "Nobody"},
        )
        self.assertEqual(res.status_code, 400)

    # -- draw -------------------------------------------------------------
    def test_draw_produces_a_bijection(self):
        res = self.client.post("/api/exchanges/" + self.exchange_id + "/draw", json={})
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertTrue(payload["ok"])
        assignment = payload["assignment"]
        self.assertEqual(len(assignment), 4)
        self.assertEqual(len(set(assignment.values())), 4)
        for giver, receiver in assignment.items():
            self.assertNotEqual(giver, receiver)

    def test_draw_is_persisted(self):
        self.client.post("/api/exchanges/" + self.exchange_id + "/draw", json={})
        data = self._get("/api/exchanges/" + self.exchange_id)
        self.assertEqual(len(data["assignment"]), 4)

    def test_impossible_exchange_reports_the_problem(self):
        res = self.client.post("/api/samples/load", json={"sample": "impossible_households"})
        eid = res.get_json()["exchange"]["id"]
        res = self.client.post("/api/exchanges/" + eid + "/draw", json={})
        payload = res.get_json()
        self.assertFalse(payload["ok"])
        ids = [f["id"] for f in payload["report"]["findings"]]
        self.assertIn("unsatisfiable", ids)

    # -- exports ----------------------------------------------------------
    def test_export_formats(self):
        self.client.post("/api/exchanges/" + self.exchange_id + "/draw", json={})
        for fmt, needle in (
            ("md", "## Findings"),
            ("csv", "giver,giver_email,receiver"),
            ("ics", "BEGIN:VEVENT"),
            ("json", '"exchange"'),
            ("sheet", "buys for"),
        ):
            res = self.client.get(
                "/api/exchanges/" + self.exchange_id + "/export?format=" + fmt
            )
            self.assertEqual(res.status_code, 200)
            self.assertIn(needle, res.get_data(as_text=True))

    # -- reveal -----------------------------------------------------------
    def test_reveal_shows_only_one_pairing(self):
        self.client.post("/api/exchanges/" + self.exchange_id + "/draw", json={})
        people = self._get("/api/exchanges/" + self.exchange_id)["exchange"]["participants"]
        code = people[0]["access_code"]
        res = self.client.get("/api/reveal?code=" + code)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["you"], people[0]["name"])
        self.assertTrue(data["drawn"])
        self.assertNotIn("assignment", data)

    def test_reveal_with_unknown_code(self):
        res = self.client.get("/api/reveal?code=ZZZZZZ")
        self.assertEqual(res.status_code, 404)

    # -- run log ----------------------------------------------------------
    def test_run_log_and_rating(self):
        res = self.client.post(
            "/api/exchanges/" + self.exchange_id + "/runs",
            json={"rating": 4, "notes": "went fine"},
        )
        self.assertEqual(res.status_code, 200)
        run_id = res.get_json()["run_id"]
        res = self.client.post(
            "/api/runs/%d/rating" % run_id, json={"rating": 5, "notes": "great"}
        )
        self.assertEqual(res.status_code, 200)
        runs = self._get("/api/runs")["runs"]
        self.assertEqual(runs[0]["rating"], 5)

    def test_rating_out_of_range_is_rejected(self):
        res = self.client.post("/api/runs/1/rating", json={"rating": 9})
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
