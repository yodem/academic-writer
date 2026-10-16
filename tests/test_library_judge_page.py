"""The blind judging page: static rules (no network, themes, RTL, accessibility, phone width) and a Node vm run with a stub DOM."""

import copy
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from html.parser import HTMLParser

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(REPO, "src", "skills", "library-eval", "references", "judge-page.html")
FIXTURES = os.path.join(REPO, "tests", "fixtures", "library-eval")
HARNESS = os.path.join(FIXTURES, "judge-harness.cjs")
SCHEMAS = os.path.join(REPO, "src", "schemas")
NODE = shutil.which("node")

VOID = {"meta", "link", "br", "hr", "img", "input", "area", "base", "col", "embed", "source", "track", "wbr"}
# The same slot and the same escaping `aw library eval page` uses (src/cli/src/library/eval/cli.ts).
SLOT = re.compile(r"""(<script\b[^>]*\bid=["']pairs["'][^>]*>)([\s\S]*?)(</script>)""", re.I)
ROUTE_WORDS = re.compile(r"trove|page-?index|route|shadow|sealed|mapping(?!_sha256)|backend", re.I)


def read(path):
    with open(path, encoding="utf-8") as stream:
        return stream.read()


def schema(name):
    return json.loads(read(os.path.join(SCHEMAS, f"library-eval-{name}.schema.json")))


def fill(template, document):
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return SLOT.sub(lambda m: m.group(1) + payload + m.group(3), template, count=1)


class Outline(HTMLParser):
    """Checks nesting and collects what the static rules need."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.problems, self.attrs, self.styles, self.scripts, self._in = [], [], [], [], [], None

    def handle_starttag(self, tag, attrs):
        self.attrs.append((tag, dict(attrs)))
        if tag not in VOID:
            self.stack.append(tag)
        if tag in ("style", "script"):
            self._in = (tag, dict(attrs), [])

    def handle_endtag(self, tag):
        if self._in and self._in[0] == tag:
            kind, attrs, parts = self._in
            (self.styles if kind == "style" else self.scripts).append((attrs, "".join(parts)))
            self._in = None
        if not self.stack or self.stack[-1] != tag:
            self.problems.append(f"unexpected </{tag}> with {self.stack[-3:]} open")
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
        else:
            self.stack.pop()

    def handle_data(self, data):
        if self._in:
            self._in[2].append(data)


def outline(html):
    parser = Outline()
    parser.feed(html)
    parser.close()
    return parser


def validator(root, ref=None):
    try:
        import jsonschema
    except ImportError:
        return None
    target = {"$ref": ref, "definitions": root["definitions"]} if ref else root
    return jsonschema.Draft7Validator(target)


def check_import(testcase, document):
    """Valid against definitions.import of the judgments schema (jsonschema when installed, a strict hand check always)."""
    check = validator(schema("judgments"), "#/definitions/import")
    if check is not None:
        errors = [error.message for error in check.iter_errors(document)]
        testcase.assertEqual(errors, [])
    testcase.assertEqual(set(document), {"schema", "eval_id", "judgments"})
    testcase.assertEqual(document["schema"], 1)
    for item in document["judgments"]:
        testcase.assertLessEqual(set(item), {"pair_id", "verdict", "note", "at"})
        testcase.assertRegex(item["pair_id"], r"^p[0-9]{2,3}$")
        testcase.assertIn(item["verdict"], ["A", "B", "same", "neither", "skip"])
        testcase.assertLessEqual(len(item.get("note", "")), 2000)


class StaticRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = read(TEMPLATE)
        cls.parsed = outline(cls.html)
        cls.css = "\n".join(text for _, text in cls.parsed.styles)
        cls.script = next(text for attrs, text in cls.parsed.scripts if "type" not in attrs)

    def test_parses_with_balanced_tags(self):
        self.assertEqual(self.parsed.problems, [])
        self.assertEqual(self.parsed.stack, [])
        self.assertTrue(self.html.lstrip().lower().startswith("<!doctype html>"))
        self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1">', self.html)
        self.assertIn('<html lang="en">', self.html)

    def test_no_external_urls_at_all(self):
        self.assertEqual(re.findall(r"https?://", self.html), [])
        for tag, attrs in self.parsed.attrs:
            for name in ("src", "href", "action", "poster", "data"):
                value = attrs.get(name)
                if value is None:
                    continue
                self.assertFalse(re.match(r"^(?:[a-z][a-z0-9+.-]*:)?//", value, re.I), f"<{tag} {name}={value}>")
            self.assertNotIn("srcset", attrs)
        self.assertNotRegex(self.css, r"@import")
        self.assertNotRegex(self.css, r"url\(\s*['\"]?\s*(?:https?:)?//")
        self.assertEqual([attrs for tag, attrs in self.parsed.attrs if tag in ("link", "iframe", "img", "object", "embed")], [])
        for forbidden in ("fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon", "importScripts", "import("):
            self.assertNotIn(forbidden, self.script)

    def test_pairs_slot_is_one_json_script(self):
        slots = [(attrs, text) for attrs, text in self.parsed.scripts if attrs.get("id") == "pairs"]
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0][0].get("type"), "application/json")
        self.assertEqual(len(SLOT.findall(self.html)), 1)
        self.assertEqual(json.loads(slots[0][1])["pairs"], [])

    def test_light_and_dark_themes_from_tokens(self):
        self.assertIn("@media (prefers-color-scheme: dark)", self.css)
        self.assertIn('name="color-scheme" content="light dark"', self.html)
        light = re.search(r":root\s*\{([^}]*)\}", self.css).group(1)
        dark = re.search(r"prefers-color-scheme: dark\)\s*\{\s*:root\s*\{([^}]*)\}", self.css).group(1)
        for token in ("--bg", "--surface", "--ink", "--muted", "--rule", "--accent", "--accent-ink", "--focus"):
            self.assertIn(token + ":", light)
            self.assertIn(token + ":", dark)
        # Component rules take colours from tokens; a raw colour outside the token blocks would break the dark theme.
        rest = self.css.replace(light, "").replace(dark, "")
        self.assertEqual(re.findall(r"#[0-9a-fA-F]{3,8}\b", rest), [])

    def test_phone_width_gutter_and_no_horizontal_scroll(self):
        self.assertRegex(self.css, r"--gutter:\s*16px")
        self.assertRegex(self.css, r"padding-inline:\s*var\(--gutter\)")
        self.assertRegex(self.css, r"html,\s*body\s*\{[^}]*overflow-x:\s*hidden")
        self.assertIn("overflow-wrap: anywhere", self.css)
        self.assertIn("minmax(0, 1fr)", self.css)
        self.assertRegex(self.css, r"@media \(min-width: 56rem\)")
        # No fixed width that could exceed a 400px screen.
        self.assertNotRegex(self.css, r"(?<![-a-z])width:\s*(?:[4-9][0-9]{2}|[0-9]{4,})px")

    def test_rtl_safe_text_and_logical_css(self):
        self.assertIn("dir: 'auto'", self.script)
        self.assertGreaterEqual(self.script.count("dir: 'auto'"), 4)
        self.assertRegex(self.css, r"border-inline-start")
        self.assertNotRegex(self.css, r"(?:margin|padding|border)-(?:left|right)\b")
        self.assertNotRegex(self.css, r"text-align:\s*(?:left|right)")
        self.assertIn("Noto Serif Hebrew", self.css)

    def test_keyboard_and_screen_reader_support(self):
        self.assertIn(":focus-visible", self.css)
        self.assertRegex(self.css, r"\.choice input:focus-visible \+ \.choice-body")
        for needle in ("aria-label", "aria-labelledby", "aria-expanded", "aria-controls", "aria-live"):
            self.assertIn(needle, self.script + self.html)
        self.assertIn('role="status"', self.html)
        self.assertIn("<legend", self.script.replace("el('legend'", "<legend"))
        self.assertRegex(self.css, r"min-height:\s*44px")
        self.assertNotIn("tabindex=\"1", self.html)

    def test_storage_adapter_is_one_marked_block_with_two_back_ends(self):
        start = self.script.index("STORAGE ADAPTER: the only block")
        end = self.script.index("END OF STORAGE ADAPTER")
        block = self.script[start:end]
        for needle in ("createSharedStore", "createLocalStore", "load()", "save(j)", "list()", "localStorage", "canDownload"):
            self.assertIn(needle, block)
        outside = self.script[:start] + self.script[end:]
        self.assertNotIn("localStorage.getItem(key)", outside)
        self.assertEqual(self.script.count("createSharedStore() ||"), 1)  # one call; the definition is the only other code use
        # Every localStorage touch sits inside a try block.
        for match in re.finditer(r"window\.localStorage", self.script):
            before = self.script[: match.start()]
            self.assertGreater(before.rfind("try {"), before.rfind("}  catch"), "localStorage outside try")
            self.assertGreater(before.rfind("try {"), before.rfind("catch (error)"), "localStorage outside try")

    def test_no_route_words_in_the_template(self):
        stripped = SLOT.sub(r"\1\3", self.html)
        self.assertEqual(ROUTE_WORDS.findall(stripped), [])

    def test_has_four_verdicts_defined(self):
        self.assertIn("VERDICTS = ['A', 'B', 'same', 'neither']", self.script)
        for title in ("A better", "B better", "Same", "Neither"):
            self.assertIn(f"title: '{title}'", self.script)


class Fixture(unittest.TestCase):
    def test_pairs_fixture_is_valid_blind_and_bilingual(self):
        document = json.loads(read(os.path.join(FIXTURES, "pairs.json")))
        check = validator(schema("pairs"))
        if check is not None:
            self.assertEqual([e.message for e in check.iter_errors(document)], [])
        text = json.dumps(document, ensure_ascii=False)
        self.assertEqual(ROUTE_WORDS.findall(text), [])
        self.assertTrue(re.search(r"[\u0590-\u05ff]", text))
        self.assertTrue(re.search(r"[A-Za-z]{4,}", text))
        self.assertEqual([p["pair_id"] for p in document["pairs"] if p["auto_same"]], ["p04"])


@unittest.skipUnless(NODE, "node is not installed")
class PageRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="judge-page-")
        cls.document = json.loads(read(os.path.join(FIXTURES, "pairs.json")))
        cls.filled = os.path.join(cls.tmp, "judge.html")
        with open(cls.filled, "w", encoding="utf-8") as stream:
            stream.write(fill(read(TEMPLATE), cls.document))
        cls.runs = {mode: cls.run_harness(mode) for mode in ("local", "shared")}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def run_harness(cls, mode):
        done = subprocess.run([NODE, HARNESS, cls.filled, mode], capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    def test_inline_script_passes_node_check(self):
        script = next(text for attrs, text in outline(read(TEMPLATE)).scripts if "type" not in attrs)
        path = os.path.join(self.tmp, "inline.js")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(script)
        done = subprocess.run([NODE, "--check", path], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_filled_page_keeps_the_data_intact_and_closes_one_script_only(self):
        tricky = copy.deepcopy(self.document)
        tricky["pairs"][0]["options"]["A"]["pages"][0]["text"] = "x </script><img src=x onerror=alert(1)> \u2028 y"
        page = fill(read(TEMPLATE), tricky)
        slot = SLOT.search(page).group(2)
        self.assertNotIn("<", slot)
        self.assertEqual(json.loads(slot), tricky)
        parsed = outline(page)
        self.assertEqual(parsed.problems, [])
        self.assertEqual(len(parsed.scripts), 2)

    def test_template_works_with_the_command_that_fills_it(self):
        html = read(TEMPLATE)
        self.assertTrue(SLOT.search(html))
        self.assertEqual(re.findall(r"trove|page-?index", SLOT.sub(r"\1\3", html), re.I), [])

    def test_every_visible_pair_has_four_verdicts_and_labels(self):
        sweep = self.runs["local"]["sweep"]
        visible = [p for p in self.document["pairs"] if not p["auto_same"]]
        self.assertEqual(len(sweep), len(visible))
        for index, (view, pair) in enumerate(zip(sweep, visible), start=1):
            self.assertEqual(view["heading"], f"Pair {index} of {len(visible)}")
            self.assertEqual([r["value"] for r in view["radios"]], ["A", "B", "same", "neither"])
            self.assertEqual({r["name"] for r in view["radios"]}, {f"verdict-{pair['pair_id']}"})
            self.assertEqual(view["fieldsets"], 1)
            self.assertEqual(view["legends"], ["Which result supports the claim better?"])
            self.assertEqual(view["claim"], {"text": pair["claim"]["text"], "dir": "auto"})
            self.assertEqual([r["heading"] for r in view["results"]], ["Result A", "Result B"])
            self.assertEqual(view["note"]["dir"], "auto")
            self.assertEqual(view["note"]["label"], 1)

    def test_text_blocks_follow_their_own_direction(self):
        first = self.runs["local"]["first"]
        for result in first["results"]:
            self.assertTrue(result["paragraphDirs"])
            self.assertEqual(set(result["paragraphDirs"]), {"auto"})
        self.assertEqual(first["results"][0]["pageLabels"], ["Page 12", "Page 13"])
        self.assertIn("וַיֹּאמֶר", first["results"][0]["text"])

    def test_long_text_collapses_and_opens(self):
        run = self.runs["local"]
        before, after = run["second_before_toggle"], run["second_after_toggle"]
        self.assertEqual([t["label"] for t in before["toggles"]], ["Show full text"])
        self.assertEqual(before["toggles"][0]["expanded"], "false")
        self.assertEqual(before["clamped"], [True, False])
        self.assertEqual(after["toggles"][0]["expanded"], "true")
        self.assertEqual(after["toggles"][0]["label"], "Show less")
        self.assertEqual(after["clamped"], [False, False])
        self.assertEqual(before["results"][1]["empty"], ["This result returned no pages."])
        self.assertIn("0 pages", before["results"][1]["meta"])

    def test_answers_are_saved_and_the_page_resumes_where_it_stopped(self):
        run = self.runs["local"]
        answered = run["first_after_answer"]
        self.assertEqual([r["value"] for r in answered["radios"] if r["checked"]], ["B"])
        self.assertEqual(answered["note"]["value"], "הערה בעברית: ב טוב יותר")
        self.assertEqual(run["fourth"]["heading"], "Pair 4 of 5")
        resumed = run["resumed"]
        self.assertEqual(resumed["heading"], "Pair 4 of 5")
        self.assertTrue(any("Welcome back" in note for note in resumed["notice"]))
        self.assertTrue(resumed["focused"])
        self.assertEqual([r["checked"] for r in resumed["radios"]], [False] * 4)
        self.assertEqual(run["resumed_prev"]["heading"], "Pair 3 of 5")
        self.assertEqual(run["resumed_prev"]["progress"], [{"value": "3", "max": "5", "label": "Pairs answered"}])
        jumped = run["after_jump"]
        self.assertEqual(jumped["heading"], "Pair 1 of 5")
        self.assertEqual([r["value"] for r in jumped["radios"] if r["checked"]], ["B"])
        self.assertEqual(jumped["note"]["value"], "הערה בעברית: ב טוב יותר")

    def test_export_is_valid_against_the_judgments_schema(self):
        for mode, run in self.runs.items():
            exported = json.loads(run["export_text"])
            check_import(self, exported)
            self.assertEqual(exported["eval_id"], self.document["eval_id"])
            self.assertEqual([(j["pair_id"], j["verdict"]) for j in exported["judgments"]], [("p01", "B"), ("p02", "same"), ("p03", "skip")], mode)
            self.assertEqual(exported["judgments"][0]["note"], "הערה בעברית: ב טוב יותר")
            self.assertEqual(exported["judgments"][1]["note"], "")
            for item in exported["judgments"]:
                self.assertRegex(item["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
            self.assertNotIn("p04", run["export_text"])  # the identical pair is marked "same" by the importer
            self.assertEqual(run["grid_first"], "Pair 1, answered")

    def test_local_back_end_downloads_and_shared_back_end_does_not(self):
        local, shared = self.runs["local"], self.runs["shared"]
        self.assertTrue(local["has_download"])
        self.assertEqual(len(local["downloads"]), 1)
        self.assertEqual(local["downloads"][0]["filename"], "judgments-ev-20261016-a.json")
        self.assertEqual(json.loads(local["downloads"][0]["text"]), json.loads(local["export_text"]))
        self.assertFalse(shared["has_download"])
        self.assertTrue(shared["has_copy"])
        self.assertEqual(shared["downloads"], [])
        self.assertEqual(shared["shared_keys"], ["judgments/p01", "judgments/p02", "judgments/p03"])

    def test_refused_storage_is_reported_not_fatal(self):
        self.assertIn("could not be stored here", self.runs["local"]["blocked_notice"])

    def test_nothing_the_judge_sees_names_a_route(self):
        for mode, run in self.runs.items():
            shown = json.dumps([run["first"], run["second_before_toggle"], run["third"], run["export_view"], run["sweep"]], ensure_ascii=False)
            # The fixture texts are neutral, so any hit would come from the page's own words.
            self.assertEqual(ROUTE_WORDS.findall(shown), [], mode)


if __name__ == "__main__":
    unittest.main()
