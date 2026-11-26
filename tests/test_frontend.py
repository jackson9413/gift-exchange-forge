"""Frontend contract tests: the markup and the script have to agree."""

import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

HTML_PATH = os.path.join(ROOT, "static", "index.html")
JS_PATH = os.path.join(ROOT, "static", "app.js")
CSS_PATH = os.path.join(ROOT, "static", "styles.css")

REQUIRED_IDS = [
    "exchange-select",
    "panel-setup",
    "panel-draw",
    "panel-readiness",
    "panel-calendar",
    "panel-reveal",
    "settings-form",
    "set-name",
    "set-budget",
    "set-draw",
    "set-shopping",
    "set-exchange",
    "set-shipping",
    "set-circle",
    "rule-household",
    "rule-group",
    "rule-repeats",
    "rule-reveal",
    "participant-form",
    "p-name",
    "p-email",
    "p-household",
    "participants-body",
    "edit-participant-form",
    "e-wishes",
    "e-purchased",
    "exclude-form",
    "x-a",
    "x-b",
    "exclusions-list",
    "btn-run-draw",
    "assignment-body",
    "score-value",
    "verdict-label",
    "axes-list",
    "findings-list",
    "fix-list",
    "run-form",
    "run-rating",
    "dates-list",
    "budget-body",
    "export-md",
    "export-csv",
    "export-ics",
    "export-json",
    "export-sheet",
    "reveal-form",
    "reveal-code",
    "reveal-result",
    "brief-input",
    "sample-list",
    "toast",
]


class FrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(HTML_PATH, "r", encoding="utf-8") as handle:
            cls.html = handle.read()
        with open(JS_PATH, "r", encoding="utf-8") as handle:
            cls.js = handle.read()
        with open(CSS_PATH, "r", encoding="utf-8") as handle:
            cls.css = handle.read()

    def test_every_required_id_exists_in_the_markup(self):
        for element_id in REQUIRED_IDS:
            self.assertIn('id="%s"' % element_id, self.html, element_id)

    def test_script_touches_every_interactive_id(self):
        for element_id in REQUIRED_IDS:
            if element_id.startswith("panel-"):
                continue  # panels are wired through the data-panel attribute
            self.assertIn('"%s"' % element_id, self.js, element_id)

    def test_no_build_markers_left_behind(self):
        for marker in ("APP_PART", "ENGINE_PART", "MARKER"):
            self.assertNotIn(marker, self.js)
            self.assertNotIn(marker, self.html)

    def test_static_assets_are_linked(self):
        self.assertIn("/static/app.js", self.html)
        self.assertIn("/static/styles.css", self.html)

    def test_script_has_no_template_literals(self):
        # A stray backtick would break the payload the build writes.
        self.assertNotIn(chr(96), self.js)

    def test_tabs_cover_every_panel(self):
        panels = set(re.findall(r'data-panel="([^"]+)"', self.html))
        for panel in panels:
            self.assertIn('id="%s"' % panel, self.html)

    def test_styles_define_the_dark_theme(self):
        self.assertIn("--bg", self.css)
        self.assertIn(".card", self.css)
        self.assertIn(".finding", self.css)

    def test_endpoints_used_by_the_script_exist_in_the_api(self):
        with open(os.path.join(ROOT, "app.py"), "r", encoding="utf-8") as handle:
            api_source = handle.read()
        routes = set(
            re.findall(r'@app\.(?:get|post|put|patch|delete)\("([^"]+)"', api_source)
        )
        used = set(re.findall(r'"(/api/[^"?]*)', self.js))
        for path in used:
            match = None
            for route in routes:
                pattern = re.sub(r"<[^>]+>", "[^/]+", route)
                if re.match("^" + pattern + "$", path) or path.endswith("/"):
                    match = route
                    break
            self.assertIsNotNone(match, "no API route matches %s" % path)


if __name__ == "__main__":
    unittest.main()
