"""Engine tests for Gift Exchange Forge."""

import datetime as dt
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import exporters  # noqa: E402
import samples  # noqa: E402
from briefparse import parse_brief  # noqa: E402
from engine import Exchange, Participant, solve_assignment  # noqa: E402
from rules import review  # noqa: E402

TODAY = dt.date.today()
D = lambda n: (TODAY + dt.timedelta(days=n)).isoformat()  # noqa: E731

BRIEF = """[Exchange]
name: Test Exchange
budget: 40
draw: {draw}
shopping: {shopping}
exchange: {exchange}
shipping: 4
circle: test-circle

[Participants]
Ada Lovelace | ada@example.com | House A
Alan Turing | alan@example.com | House A
Grace Hopper | grace@example.com | House B
Edsger Dijkstra | edsger@example.com | House B

[Exclude]
Ada Lovelace | Grace Hopper

[Wishlist]
Ada Lovelace | Book | 25.00 | blue cover
""".format(draw=D(7), shopping=D(14), exchange=D(21))


def make_exchange(participants, **kwargs):
    ex = Exchange(id="test", name="Test", **kwargs)
    ex.participants = participants
    return ex


def person(pid, name, household="", groups=None, code="CODE", wishes=None, purchased=None):
    return Participant(
        id=pid,
        name=name,
        email=pid + "@example.com",
        household=household,
        groups=groups or [],
        access_code=code,
        wishes=wishes or [],
        purchased=purchased or {},
    )


class BriefParserTests(unittest.TestCase):
    def test_parses_sections(self):
        ex, warnings = parse_brief(BRIEF)
        self.assertEqual(ex.name, "Test Exchange")
        self.assertEqual(ex.budget, 40)
        self.assertEqual(ex.shipping_days, 4)
        self.assertEqual(ex.circle, "test-circle")
        self.assertEqual(len(ex.participants), 4)
        self.assertEqual(ex.draw_date, TODAY + dt.timedelta(days=7))
        self.assertEqual(ex.shopping_deadline, TODAY + dt.timedelta(days=14))
        self.assertEqual(ex.exchange_date, TODAY + dt.timedelta(days=21))
        self.assertEqual(warnings, [])

    def test_resolves_exclusions_to_ids(self):
        ex, _ = parse_brief(BRIEF)
        self.assertEqual(len(ex.exclusions), 1)
        a, b = ex.exclusions[0]
        self.assertEqual(ex.name_of(a), "Ada Lovelace")
        self.assertEqual(ex.name_of(b), "Grace Hopper")

    def test_attaches_wishlists(self):
        ex, _ = parse_brief(BRIEF)
        ada = [p for p in ex.participants if p.name == "Ada Lovelace"][0]
        self.assertEqual(len(ada.wishes), 1)
        self.assertEqual(ada.wishes[0].item, "Book")
        self.assertEqual(ada.wishes[0].price, 25.0)

    def test_generates_access_codes(self):
        ex, _ = parse_brief(BRIEF)
        codes = [p.access_code for p in ex.participants]
        self.assertEqual(len(set(codes)), 4)
        self.assertTrue(all(codes))

    def test_warns_on_unknown_section(self):
        ex, warnings = parse_brief("[Nonsense]\nhello\n")
        self.assertTrue(any("Nonsense" in w for w in warnings))

    def test_warns_on_unknown_exclusion(self):
        _, warnings = parse_brief(
            "[Participants]\nAda | ada@example.com\n\n[Exclude]\nAda | Nobody\n"
        )
        self.assertTrue(any("Nobody" in w for w in warnings))

    def test_warns_on_bad_date(self):
        _, warnings = parse_brief("[Exchange]\ndraw: not-a-date\n")
        self.assertTrue(any("not-a-date" in w for w in warnings))

    def test_empty_brief_does_not_crash(self):
        ex, warnings = parse_brief("")
        self.assertEqual(len(ex.participants), 0)
        self.assertTrue(warnings)


class SolverTests(unittest.TestCase):
    def test_draw_is_a_permutation_without_self_draws(self):
        ex, _ = parse_brief(BRIEF)
        result = solve_assignment(ex, seed=3)
        self.assertTrue(result.ok)
        self.assertEqual(len(result.assignment), len(ex.participants))
        self.assertEqual(len(set(result.assignment.values())), len(ex.participants))
        for giver, receiver in result.assignment.items():
            self.assertNotEqual(giver, receiver)

    def test_household_rule_is_respected(self):
        ex, _ = parse_brief(BRIEF)
        result = solve_assignment(ex, seed=5)
        self.assertTrue(result.ok)
        for giver, receiver in result.assignment.items():
            self.assertNotEqual(ex.household_of(giver), ex.household_of(receiver))

    def test_exclusion_is_respected(self):
        ex, _ = parse_brief(BRIEF)
        result = solve_assignment(ex, seed=5)
        self.assertTrue(result.ok)
        a, b = ex.exclusions[0]
        self.assertNotEqual(result.assignment[a], b)
        self.assertNotEqual(result.assignment[b], a)

    def test_impossible_exchange_reports_zero_candidates(self):
        people = [
            person("a", "A", "H1"),
            person("b", "B", "H1"),
            person("c", "C", "H1"),
            person("d", "D", "H1"),
        ]
        ex = make_exchange(people)
        result = solve_assignment(ex, seed=1)
        self.assertFalse(result.ok)
        self.assertTrue(result.zero_candidate)
        self.assertTrue(result.relaxations)

    def test_hall_violator_group_is_named(self):
        # Three people in one household, two in another: the three can only
        # draw the two, which is a Hall violation with no single blocked giver.
        people = [
            person("a", "A", "H1"),
            person("b", "B", "H1"),
            person("c", "C", "H1"),
            person("d", "D", "H2"),
            person("e", "E", "H2"),
        ]
        ex = make_exchange(people)
        result = solve_assignment(ex, seed=1)
        self.assertFalse(result.ok)
        self.assertEqual(result.zero_candidate, [])
        self.assertTrue(result.blocked_groups)
        self.assertEqual(len(result.blocked_groups[0]), 3)

    def test_history_pair_is_avoided_when_possible(self):
        people = [
            person("a", "A"),
            person("b", "B"),
            person("c", "C"),
            person("d", "D"),
        ]
        ex = make_exchange(people)
        result = solve_assignment(ex, history_pairs=[("a", "b"), ("c", "d")], seed=2)
        self.assertTrue(result.ok)
        for giver, receiver in result.assignment.items():
            self.assertNotIn((giver, receiver), [("a", "b"), ("c", "d")])

    def test_forced_repeat_reports_relaxation(self):
        people = [
            person("a", "A"),
            person("b", "B"),
            person("c", "C"),
            person("d", "D"),
        ]
        ex = make_exchange(people)
        ex.exclusions = [
            ("a", "b"), ("b", "a"),
            ("a", "c"), ("c", "a"),
            ("c", "d"), ("d", "c"),
            ("b", "d"), ("d", "b"),
        ]
        result = solve_assignment(ex, history_pairs=[("a", "d")], seed=9)
        self.assertFalse(result.ok)
        self.assertTrue(result.repeat_pairs)
        self.assertTrue(any("no-repeat" in r for r in result.relaxations))

    def test_group_rule_blocks_same_group(self):
        people = [
            person("a", "A", "", ["bookclub"]),
            person("b", "B", "", ["bookclub"]),
            person("c", "C"),
            person("d", "D"),
        ]
        ex = make_exchange(people, no_same_group=True)
        result = solve_assignment(ex, seed=4)
        self.assertTrue(result.ok)
        self.assertNotEqual(result.assignment["a"], "b")
        self.assertNotEqual(result.assignment["b"], "a")


class RuleTests(unittest.TestCase):
    def test_clean_exchange_scores_high(self):
        ex, _ = parse_brief(BRIEF)
        result = solve_assignment(ex, seed=3)
        report = review(ex, assignment=result.assignment, solve=result)
        self.assertGreater(report["score"], 85)
        self.assertEqual(report["verdict"], "ready_to_draw")

    def test_missing_exchange_date_is_critical(self):
        ex, _ = parse_brief(BRIEF)
        ex.exchange_date = None
        report = review(ex)
        ids = [f["id"] for f in report["findings"]]
        self.assertIn("missing_exchange_date", ids)
        self.assertLessEqual(report["score"], 45)

    def test_shipping_window_too_short(self):
        ex, _ = parse_brief(BRIEF)
        ex.draw_date = TODAY
        ex.exchange_date = TODAY + dt.timedelta(days=2)
        ex.shipping_days = 7
        report = review(ex)
        ids = [f["id"] for f in report["findings"]]
        self.assertIn("shipping_window_too_short", ids)

    def test_wish_over_budget(self):
        ex, _ = parse_brief(BRIEF)
        ex.budget = 10
        report = review(ex)
        self.assertIn("wish_over_budget", [f["id"] for f in report["findings"]])

    def test_purchase_over_budget(self):
        ex, _ = parse_brief(BRIEF)
        ex.budget = 20
        ex.participants[0].purchased = {"Sneakers": 120.0}
        report = review(ex)
        self.assertIn("purchase_over_budget", [f["id"] for f in report["findings"]])

    def test_missing_access_code_caps_score(self):
        ex, _ = parse_brief(BRIEF)
        ex.participants[0].access_code = ""
        report = review(ex)
        self.assertIn("missing_access_code", [f["id"] for f in report["findings"]])
        self.assertLessEqual(report["score"], 60)

    def test_duplicate_names_are_flagged(self):
        ex, _ = parse_brief(BRIEF)
        ex.participants.append(person("z", "Ada Lovelace"))
        report = review(ex)
        self.assertIn("duplicate_name", [f["id"] for f in report["findings"]])

    def test_draw_after_exchange_is_critical(self):
        ex, _ = parse_brief(BRIEF)
        ex.draw_date = TODAY + dt.timedelta(days=30)
        report = review(ex)
        self.assertIn("draw_after_exchange", [f["id"] for f in report["findings"]])
        self.assertLessEqual(report["score"], 35)

    def test_every_finding_has_evidence_why_and_fix(self):
        ex, _ = parse_brief(BRIEF)
        ex.exchange_date = None
        ex.budget = None
        report = review(ex)
        self.assertTrue(report["findings"])
        for finding in report["findings"]:
            self.assertTrue(finding["evidence"])
            self.assertTrue(finding["why"])
            self.assertTrue(finding["fix"])
            self.assertIn(finding["severity"], ("critical", "high", "medium", "low"))

    def test_fix_plan_is_ordered_by_severity(self):
        ex, _ = parse_brief(BRIEF)
        ex.exchange_date = None
        report = review(ex)
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        ranks = [order[s["severity"]] for s in report["fix_plan"]]
        self.assertEqual(ranks, sorted(ranks))

    def test_axes_cover_the_whole_score(self):
        ex, _ = parse_brief(BRIEF)
        report = review(ex)
        self.assertEqual(len(report["axes"]), 5)
        self.assertAlmostEqual(sum(a["weight"] for a in report["axes"]), 1.0, places=5)


class ExporterTests(unittest.TestCase):
    def setUp(self):
        self.ex, _ = parse_brief(BRIEF)
        self.result = solve_assignment(self.ex, seed=3)
        self.report = review(self.ex, assignment=self.result.assignment, solve=self.result)

    def test_markdown_has_every_section(self):
        text = exporters.to_markdown(self.ex, self.report, self.result.assignment)
        for heading in ("# Test Exchange", "## Score by axis", "## Draw", "## Dates", "## Findings"):
            self.assertIn(heading, text)

    def test_csv_has_header_and_one_row_per_participant(self):
        text = exporters.to_csv(self.ex, self.result.assignment)
        lines = [line for line in text.strip().splitlines() if line]
        self.assertEqual(len(lines), len(self.ex.participants) + 1)
        self.assertIn("giver", lines[0])
        self.assertIn("receiver", lines[0])

    def test_ics_has_three_events(self):
        text = exporters.to_ics(self.ex, self.result.assignment)
        self.assertEqual(text.count("BEGIN:VEVENT"), 3)
        self.assertIn("DTSTART;VALUE=DATE:", text)
        self.assertTrue(text.rstrip().endswith("END:VCALENDAR"))

    def test_json_round_trips(self):
        text = exporters.to_json(self.ex, self.report, self.result.assignment)
        data = json.loads(text)
        self.assertEqual(data["exchange"]["name"], "Test Exchange")
        self.assertEqual(len(data["assignment"]), len(self.ex.participants))

    def test_participant_sheet_lists_codes(self):
        text = exporters.to_participant_sheet(self.ex, self.result.assignment)
        self.assertIn(self.ex.participants[0].access_code, text)


class SampleTests(unittest.TestCase):
    def test_every_sample_builds(self):
        for sample_id in samples.sample_ids():
            ex, warnings, history = samples.build_sample(sample_id)
            self.assertTrue(ex.participants, sample_id)
            self.assertIsInstance(warnings, list)
            self.assertIsInstance(history, list)

    def test_sample_verdicts_match_expectations(self):
        for spec in samples.SAMPLE_SPECS:
            sample_id, expect = spec[0], spec[3]
            ex, _, history = samples.build_sample(sample_id)
            result = solve_assignment(ex, history_pairs=history)
            report = review(
                ex,
                assignment=result.assignment if result.ok else {},
                solve=result,
                history_pairs=history,
            )
            self.assertEqual(report["verdict"], expect, sample_id)

    def test_control_sample_is_clean(self):
        ex, _, history = samples.build_sample("family_christmas")
        result = solve_assignment(ex, history_pairs=history)
        report = review(ex, assignment=result.assignment, solve=result, history_pairs=history)
        high = [f["id"] for f in report["findings"] if f["severity"] in ("critical", "high")]
        self.assertEqual(high, [])


if __name__ == "__main__":
    unittest.main()
