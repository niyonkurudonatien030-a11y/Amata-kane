"""Consistency checks between the frontend code and the backend: do the URLs and button handlers it uses actually exist?"""
import re
import unittest
from pathlib import Path

from tests.helpers import BaseCase

JS = Path(__file__).resolve().parent.parent / "frontend" / "js"


def js_sources():
    return {p.name: p.read_text() for p in JS.glob("*.js")}


class ContractTests(BaseCase):
    @staticmethod
    def first_args(src):
        """Yield (verb, leading string literal) for each api.<verb>('...') call. Calls whose path is a variable are skipped."""
        for m in re.finditer(r"api\.(get|post|patch|put|del|upload)\(\s*(`[^`]*`|'[^']*'|\"[^\"]*\")", src):
            yield m.group(1), m.group(2)

    @staticmethod
    def normalise(arg):
        """`/jobs/${a}/${b}` -> /jobs/X/X ;  '/listings/' -> /listings/X (an id is appended in the code)"""
        arg = arg.strip("'\"`")
        arg = re.sub(r"\$\{(?:[^{}]|\{[^{}]*\})*\}", "X", arg)
        arg = arg.split("?")[0]
        return arg + "X" if arg.endswith("/") else arg

    def test_every_api_path_used_by_the_frontend_exists(self):
        rules = [(r.rule.split("/"), r.methods) for r in self.app.url_map.iter_rules() if r.rule.startswith("/api/")]
        verbs = {"get": "GET", "post": "POST", "patch": "PATCH", "put": "PUT", "del": "DELETE", "upload": "POST"}

        def matches(call_parts, rule_parts):
            if len(call_parts) != len(rule_parts):
                return False
            return all(c == r or (r.startswith("<")) or c == "X" for c, r in zip(call_parts, rule_parts))

        calls, missing = 0, []
        for name, text in js_sources().items():
            for verb, arg in self.first_args(text):
                calls += 1
                path = "/api" + self.normalise(arg)
                parts = path.split("/")
                if not any(matches(parts, rp) and verbs[verb] in m for rp, m in rules):
                    missing.append((name, verbs[verb], arg))
        self.assertGreater(calls, 40)
        self.assertEqual(missing, [], f"Frontend calls endpoints that do not exist: {str(missing)[:600]}")

    def test_every_data_act_has_a_handler(self):
        src = js_sources()
        used = set()
        for text in src.values():
            used |= set(re.findall(r'data-act="(\w+)"', text))
        handlers = set()
        for name in ("deal.js", "misc.js"):
            block = src[name].split("export const actions = {", 1)[1]
            handlers |= set(re.findall(r"^  (\w+):", block, flags=re.M))
        app_block = re.search(r"const ACTIONS = \{(.*?)\};", src["app.js"], flags=re.S).group(1)
        handlers |= set(re.findall(r"\b(\w+)\b", app_block))
        missing = sorted(a for a in used if a not in handlers)
        self.assertEqual(missing, [], f"Buttons without handlers: {missing}")

    def test_deal_actions_have_handlers_for_every_server_action(self):
        """Every action string the backend can offer a user must have a button definition in deal.js."""
        body = (Path(__file__).resolve().parent.parent / "backend/services/transactions.py").read_text()
        body = body.split("def actions_for")[1].split("def detail")[0]
        server = set()
        for line in body.splitlines():
            if "a.append(" in line or "a +=" in line:
                server |= set(re.findall(r'"([a-z_]+)"', line))
        server -= {"seller", "buyer", "carrier", "driver"}
        known_ui = set(re.findall(r"^  (\w+):", js_sources()["deal.js"].split("const dealActions = {")[1], flags=re.M))
        shown_elsewhere = {"upload_evidence", "ai_summary"}
        self.assertGreaterEqual(len(server), 12)
        for action in server:
            self.assertTrue(action in known_ui or action in shown_elsewhere, f"no UI handler for server action '{action}'")

    def test_frontend_files_have_no_inline_styles_or_scripts(self):
        for p in (JS.parent).glob("*.html"):
            t = p.read_text()
            self.assertNotIn('style="', t)
            self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)", t))
        for name, text in js_sources().items():
            self.assertNotIn('style="', text, f"{name} has an inline style that the CSP would block")


if __name__ == "__main__":
    unittest.main()
