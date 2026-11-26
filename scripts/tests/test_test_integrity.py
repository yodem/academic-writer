import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

CORE = pathlib.Path(__file__).resolve().parents[1] / "test_integrity.py"
LISTER = (
    "import json, os, sys\n"
    "if os.path.exists('crash'):\n    sys.exit(3)\n"
    "if os.path.exists('garbage'):\n    print('not json'); sys.exit(0)\n"
    "if os.path.exists('rewrite.json'):\n"
    "    for p, c in json.load(open('rewrite.json')).items():\n        open(p, 'w').write(c)\n"
    "for line in open('tests.jsonl'):\n    sys.stdout.write(line)\n"
)
CONFIG = {
    "maintainers": ["boss"],
    "label": "tests-removed",
    "suites": [{"name": "fake", "cwd": ".", "cmd": ["python3", "lister.py"], "format": "jsonl"}],
    "guarded": [".github/workflows/**", "scripts/test_integrity.py"],
    "guarded_package_scripts": ["package.json"],
}
REASON = " -- flaky upstream, replaced by an integration test"


def jl(*items):
    return "".join(json.dumps({"id": i, "skipped": s}) + "\n" for i, s in items)


def event(login, label="tests-removed"):
    return {"event": "labeled", "label": {"name": label}, "actor": {"login": login}}


class GateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = os.path.join(self.tmp, "head")
        os.makedirs(self.repo)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.write("lister.py", LISTER)
        self.write("tests.jsonl", jl(("a.py::T.one", False), ("a.py::T.two", False)))
        self.write("a.py", "class T:\n    def one(self):\n        pass\n    def two(self):\n        pass\n")
        self.write(".github/workflows/ci.yml", "name: x\n")
        self.write("package.json", json.dumps({"scripts": {"test": "node --test"}}))
        self.cfg = os.path.join(self.tmp, "cfg.json")
        self.dump(self.cfg, CONFIG)
        self.commit("base")
        self.base_tree = os.path.join(self.tmp, "base")
        self.git("worktree", "add", "-q", "--detach", self.base_tree, "HEAD")
        self.base_ref = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"], check=True,
                                       capture_output=True, text=True).stdout.strip()

    def git(self, *args):
        subprocess.run(["git", "-C", self.repo] + list(args), check=True, capture_output=True)

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def dump(self, path, obj):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f)

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def run_gate(self, body=None, labels=None, events=None, base_ref=None, extra=()):
        argv = [sys.executable, str(CORE), "run", "--config", self.cfg, "--base-tree", self.base_tree,
                "--head-tree", self.repo, "--base-ref", base_ref or self.base_ref]
        if isinstance(labels, str):
            labels = [x for x in labels.split(",") if x]  # fixtures give names; CI writes a JSON array
        for flag, content, name in (("--pr-body-file", body, "body.txt"), ("--labels-file", labels, "labels.json"),
                                    ("--label-events-file", events, "events.json")):
            if content is not None:
                path = os.path.join(self.tmp, name)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content if isinstance(content, str) else json.dumps(content))
                argv += [flag, path]
        proc = subprocess.run(argv + list(extra), capture_output=True, text=True)
        return proc.returncode, proc.stdout + proc.stderr

    def head_tests(self, *items):
        self.write("tests.jsonl", jl(*items))
        self.commit("head")


class Verdicts(GateCase):
    def test_unchanged_passes(self):
        self.write("note.txt", "x")
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)
        self.assertIn("test-integrity: OK base=2 head=2", out)

    def test_added_test_passes(self):
        self.head_tests(("a.py::T.one", False), ("a.py::T.two", False), ("a.py::T.three", False))
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)
        self.assertIn("base=2 head=3", out)

    def test_removed_test_fails_and_names_it(self):
        self.head_tests(("a.py::T.one", False))
        code, out = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("fake::a.py::T.two", out)

    def test_newly_skipped_fails_and_names_it(self):
        self.head_tests(("a.py::T.one", True), ("a.py::T.two", False))
        code, out = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("newly skipped on head: fake::a.py::T.one", out)

    def test_exempted_with_maintainer_label_passes(self):
        self.head_tests(("a.py::T.one", False))
        body = "Intro\ntests-removed: fake::a.py::T.two — flaky upstream, replaced\n"
        code, out = self.run_gate(body, "tests-removed", [event("someone"), event("boss")])
        self.assertEqual(code, 0, out)

    def test_exemption_with_double_dash_passes(self):
        self.head_tests(("a.py::T.one", False))
        body = "tests-removed: fake::a.py::T.two" + REASON
        code, out = self.run_gate(body, "tests-removed", [event("boss")])
        self.assertEqual(code, 0, out)

    def test_exemption_without_label_fails(self):
        self.head_tests(("a.py::T.one", False))
        body = "tests-removed: fake::a.py::T.two" + REASON
        code, out = self.run_gate(body, "", [])
        self.assertEqual(code, 1)
        self.assertIn("fake::a.py::T.two", out)

    def test_label_by_non_maintainer_fails(self):
        self.head_tests(("a.py::T.one", False))
        body = "tests-removed: fake::a.py::T.two" + REASON
        code, _ = self.run_gate(body, "tests-removed", [event("boss"), event("intruder")])
        self.assertEqual(code, 1)

    def test_exemption_for_non_missing_id_warns(self):
        self.write("note.txt", "x")
        self.commit("head")
        body = "tests-removed: fake::a.py::T.one" + REASON
        code, out = self.run_gate(body, "tests-removed", [event("boss")])
        self.assertEqual(code, 0, out)
        self.assertIn("warning", out)
        self.assertIn("fake::a.py::T.one", out)

    def test_exemption_does_not_cover_other_missing_ids(self):
        self.head_tests()
        self.write("tests.jsonl", jl(("a.py::T.new", False)))
        self.commit("head2")
        body = "tests-removed: fake::a.py::T.two" + REASON
        code, out = self.run_gate(body, "tests-removed", [event("boss")])
        self.assertEqual(code, 1)
        self.assertIn("fake::a.py::T.one", out)
        self.assertNotIn("missing on head: fake::a.py::T.two", out)

    def test_guarded_path_without_label_fails(self):
        self.write(".github/workflows/new.yml", "name: y\n")
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn(".github/workflows/new.yml", out)

    def test_guarded_path_with_maintainer_label_passes(self):
        self.write(".github/workflows/new.yml", "name: y\n")
        self.commit("head")
        code, out = self.run_gate("", "tests-removed", [event("boss")])
        self.assertEqual(code, 0, out)

    def test_package_scripts_change_without_label_fails(self):
        self.write("package.json", json.dumps({"scripts": {"test": "echo ok"}}))
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("package.json (scripts changed)", out)

    def test_package_non_script_change_passes(self):
        self.write("package.json", json.dumps({"scripts": {"test": "node --test"}, "version": "2"}))
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)

    def test_concatenated_event_pages_use_latest_label_event(self):
        self.head_tests(("a.py::T.one", False))
        body = "tests-removed: fake::a.py::T.two" + REASON
        pages = json.dumps([event("boss")]) + json.dumps([event("intruder")])
        code, _ = self.run_gate(body, "tests-removed", pages)
        self.assertEqual(code, 1)


class Hardening(GateCase):
    def test_non_ascii_workflow_name_is_guarded(self):
        self.write(".github/workflows/d\u00e9ploy.yml", "name: z\n")
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("d\u00e9ploy.yml", out)

    def test_moving_guarded_workflow_out_is_guarded(self):
        os.makedirs(os.path.join(self.repo, "docs"))
        self.git("mv", ".github/workflows/ci.yml", "docs/ci.yml")
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn(".github/workflows/ci.yml", out)

    def test_forged_lister_output_is_caught_by_source_check(self):
        self.write("a.py", "class T:\n    def one(self):\n        pass\n")  # test two deleted, lister still lists it
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn("missing on head (not found in source): fake::a.py::T.two", out)

    def test_head_lister_cannot_rewrite_judge_inputs(self):
        self.head_tests(("a.py::T.one", False))
        paths = {n: os.path.join(self.tmp, n) for n in ("body.txt", "labels.json", "events.json")}
        self.write("rewrite.json", json.dumps({
            paths["body.txt"]: "tests-removed: fake::a.py::T.two" + REASON,
            paths["labels.json"]: json.dumps(["tests-removed"]),
            paths["events.json"]: json.dumps([event("boss")])}))
        self.commit("head2")
        code, out = self.run_gate("", "", "[]")
        self.assertEqual(code, 1, out)
        self.assertIn("fake::a.py::T.two", out)

    def test_head_lister_cannot_forge_source_via_working_tree(self):
        self.write("a.py", "class T:\n    def one(self):\n        pass\n")  # test two deleted, committed
        self.write("rewrite.json", json.dumps({os.path.join(self.repo, "a.py"):
                                               "class T:\n    def one(self): pass\n    def two(self): pass\n"}))
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 1, out)
        self.assertIn("missing on head (not found in source): fake::a.py::T.two", out)

    def test_label_name_containing_comma_is_not_the_label(self):
        self.head_tests(("a.py::T.one", False))
        body = "tests-removed: fake::a.py::T.two" + REASON
        code, _ = self.run_gate(body, ["foo,tests-removed"], [event("boss")])
        self.assertEqual(code, 1)

    def test_exemption_id_with_spaces_and_arrows(self):
        ti = Parsers.load(self)
        tid = "vitest::web/x.test.ts::suite > does a thing"
        got, _ = ti.exemptions("tests-removed: " + tid + " \u2014 replaced by e2e", {tid})
        self.assertEqual(got, {tid: "replaced by e2e"})

    def test_exemption_for_id_containing_separator_uses_longest_id(self):
        ti = Parsers.load(self)
        got, _ = ti.exemptions("tests-removed: s::f::a -- b -- long enough reason", {"s::f::a", "s::f::a -- b"})
        self.assertEqual(got, {"s::f::a -- b": "long enough reason"})

    def test_forged_head_list_file_is_caught_by_committed_source(self):
        self.write("a.py", "class T:\n    def one(self):\n        pass\n")
        self.commit("head")
        forged = os.path.join(self.tmp, "forged.jsonl")
        with open(forged, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps({"suite": "fake", "id": i, "skipped": False}) + "\n"
                            for i in ("fake::a.py::T.one", "fake::a.py::T.two")))
        code, out = self.run_gate(extra=["--head-list", forged])
        self.assertEqual(code, 1, out)
        self.assertIn("not found in source", out)

    def test_replace_ref_does_not_change_source_check(self):
        base_blob = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD:a.py"], capture_output=True,
                                   text=True, check=True).stdout.strip()
        self.write("a.py", "class T:\n    def one(self):\n        pass\n")
        self.commit("head")
        head_blob = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD:a.py"], capture_output=True,
                                   text=True, check=True).stdout.strip()
        self.git("replace", head_blob, base_blob)  # a plain `git show` would now serve the base content
        code, out = self.run_gate()
        self.assertEqual(code, 1, out)
        self.assertIn("not found in source", out)

    def test_lister_timeout_is_2(self):
        slow = dict(CONFIG, suites=[dict(CONFIG["suites"][0], cmd=["python3", "-c", "import time; time.sleep(30)"],
                                         timeout_s=1)])
        self.dump(self.cfg, slow)
        code, out = self.run_gate()
        self.assertEqual(code, 2)
        self.assertIn("timed out", out)

    def test_absent_discovery_root_lists_zero_and_shows_removed_on_head(self):
        def tree(name, with_extra):
            root = os.path.join(self.tmp, name)
            for d in (["tests", "extra"] if with_extra else ["tests"]):
                os.makedirs(os.path.join(root, d))
                with open(os.path.join(root, d, "test_%s.py" % d), "w", encoding="utf-8") as f:
                    f.write("import unittest\nclass A(unittest.TestCase):\n    def test_a(self):\n        pass\n")
            return root
        cfg = dict(CONFIG, suites=[{"name": "u", "cwd": ".", "format": "jsonl", "verify": "none",
                                    "cmd": ["python3", "{core}", "list-unittest", "tests", "extra"]}])
        path = os.path.join(self.tmp, "roots.json")
        self.dump(path, cfg)
        lists = {}
        for name, with_extra in (("full", True), ("partial", False)):
            out = os.path.join(self.tmp, name + ".jsonl")
            proc = subprocess.run([sys.executable, str(CORE), "list", "--config", path, "--tree",
                                   tree(name, with_extra), "--out", out], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            lists[name] = out
        self.cfg = path
        # base lacks a root: fine (only adds); head lacks a root the base has: its tests are missing
        code, out = self.run_gate(extra=["--base-list", lists["partial"], "--head-list", lists["full"]])
        self.assertEqual(code, 0, out)
        code, out = self.run_gate(extra=["--base-list", lists["full"], "--head-list", lists["partial"]])
        self.assertEqual(code, 1)
        self.assertIn("u::extra/test_extra.py::A.test_a", out)


class Parsers(GateCase):
    def load(self):
        sys.path.insert(0, str(CORE.parent))
        try:
            import test_integrity as ti
        finally:
            sys.path.pop(0)
        return ti

    def test_exemption_regex_is_linear_on_dash_runs(self):
        ti = self.load()
        import time
        start = time.time()
        self.assertEqual(ti.exemptions("tests-removed: x " + "-" * 5000 + "!", {"x"})[0], {})
        self.assertEqual(ti.exemptions("tests-removed: " + "- " * 5000, {"x"})[0], {})
        self.assertLess(time.time() - start, 0.5)

    def test_exemption_forms(self):
        ti = self.load()
        ids = {"a::b"}
        self.assertEqual(ti.exemptions("tests-removed: a::b \u2014 a real reason", ids)[0], {"a::b": "a real reason"})
        self.assertEqual(ti.exemptions("tests-removed: a::b -- a real reason", ids)[0], {"a::b": "a real reason"})
        self.assertEqual(ti.exemptions("tests-removed: a::b -- short", ids)[0], {})
        self.assertEqual(ti.exemptions("tests-removed: a::b -- short", ids)[1], ["a::b -- short"])

    def test_oversized_pr_body_is_2(self):
        code, out = self.run_gate("x" * 70000)
        self.assertEqual(code, 2, out)

    def test_playwright_describe_titles_keep_ids_distinct(self):
        ti = self.load()

        def describe(title):
            return {"title": title, "file": "x.spec.ts", "specs": [{"title": "works", "file": "x.spec.ts", "tests": [
                {"projectName": "p", "expectedStatus": "passed", "annotations": []}]}]}
        payload = {"config": {"rootDir": "/repo"},
                   "suites": [{"title": "x.spec.ts", "file": "x.spec.ts", "suites": [describe("A"), describe("B")]}]}
        got = [i for i, _ in ti._parse_playwright(json.dumps(payload), "/repo")]
        self.assertEqual(got, ["x.spec.ts::p::A > works", "x.spec.ts::p::B > works"])

    def test_duplicate_ids_are_2(self):
        self.write("tests.jsonl", jl(("a.py::T.one", False), ("a.py::T.one", False)))
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 2, out)
        self.assertIn("duplicate test id", out)

    def test_same_named_modules_in_two_roots_are_both_listed(self):
        tree = os.path.join(self.tmp, "two")
        for d in ("r1", "r2"):
            os.makedirs(os.path.join(tree, d))
            with open(os.path.join(tree, d, "test_a.py"), "w", encoding="utf-8") as f:
                f.write("import unittest\nclass A(unittest.TestCase):\n    def test_a(self):\n        pass\n")
        proc = subprocess.run([sys.executable, str(CORE), "list-unittest", "r1", "r2"], cwd=tree,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        ids = [json.loads(line)["id"] for line in proc.stdout.splitlines()]
        self.assertEqual(ids, ["r1/test_a.py::A.test_a", "r2/test_a.py::A.test_a"])


SKIP = "@unittest." + "skip"  # built from parts so this file's own marker count does not move


class SkipMarkers(GateCase):
    def add_marker(self):
        self.write("a.py", "class T:\n    def one(self):\n        pass\n    %s('x')\n    def two(self):\n        pass\n" % SKIP)
        self.commit("head")

    def test_added_marker_fails_even_when_list_says_not_skipped(self):
        self.add_marker()
        code, out = self.run_gate()
        self.assertEqual(code, 1, out)
        self.assertIn("skip markers added: a.py (+", out)

    def test_added_marker_passes_with_maintainer_label(self):
        self.add_marker()
        code, out = self.run_gate("", "tests-removed", [event("boss")])
        self.assertEqual(code, 0, out)

    def test_removed_marker_is_fine(self):
        self.write("a.py", "class T:\n    %s('x')\n    def one(self):\n        pass\n    def two(self):\n        pass\n" % SKIP)
        self.git("add", "-A")
        self.git("commit", "-q", "--amend", "-m", "base")  # base now has the marker
        self.base_ref = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"], check=True,
                                       capture_output=True, text=True).stdout.strip()
        self.git("worktree", "remove", "--force", self.base_tree)
        self.git("worktree", "add", "-q", "--detach", self.base_tree, self.base_ref)
        self.write("a.py", "class T:\n    def one(self):\n        pass\n    def two(self):\n        pass\n")
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)


class HeadSha(GateCase):
    def head(self):
        return subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"], check=True, capture_output=True,
                              text=True).stdout.strip()

    def make_list(self, sha=None):
        out = os.path.join(self.tmp, "hl.jsonl")
        argv = [sys.executable, str(CORE), "list", "--config", self.cfg, "--tree", self.repo, "--out", out]
        if sha:
            argv += ["--head-sha", sha]
        proc = subprocess.run(argv, capture_output=True, text=True)
        return proc.returncode, out, proc.stderr

    def test_matching_sha_passes(self):
        self.write("note.txt", "x")
        self.commit("head")
        sha = self.head()
        rc, out, _ = self.make_list(sha)
        self.assertEqual(rc, 0)
        code, text = self.run_gate(extra=["--head-list", out, "--head-sha", sha])
        self.assertEqual(code, 0, text)

    def test_list_for_another_sha_is_2(self):
        self.write("note.txt", "x")
        self.commit("head")
        rc, out, _ = self.make_list(self.head())
        self.assertEqual(rc, 0)
        code, text = self.run_gate(extra=["--head-list", out, "--head-sha", "0" * 40])
        self.assertEqual(code, 2, text)

    def test_list_without_meta_is_2_when_sha_given(self):
        self.write("note.txt", "x")
        self.commit("head")
        rc, out, _ = self.make_list()
        self.assertEqual(rc, 0)
        code, text = self.run_gate(extra=["--head-list", out, "--head-sha", self.head()])
        self.assertEqual(code, 2, text)

    def test_list_refuses_wrong_tree_head(self):
        rc, _, err = self.make_list("1" * 40)
        self.assertEqual(rc, 2, err)


class ConfigValidation(GateCase):
    def test_bad_configs_are_2(self):
        good = CONFIG["suites"][0]
        bad = {
            "empty name": dict(CONFIG, suites=[dict(good, name="")]),
            "duplicate name": dict(CONFIG, suites=[good, dict(good)]),
            "empty cmd": dict(CONFIG, suites=[dict(good, cmd=[])]),
            "non-string cmd": dict(CONFIG, suites=[dict(good, cmd=["python3", 5])]),
            "bad cwd": dict(CONFIG, suites=[dict(good, cwd=3)]),
            "zero timeout": dict(CONFIG, suites=[dict(good, timeout_s=0)]),
            "bad verify": dict(CONFIG, suites=[dict(good, verify="fuzzy")]),
            "maintainers not strings": dict(CONFIG, maintainers=[1]),
            "guarded not list": dict(CONFIG, guarded="x"),
            "package scripts not strings": dict(CONFIG, guarded_package_scripts=[2]),
            "bad regex": dict(CONFIG, skip_markers=["("]),
            "no suites": dict(CONFIG, suites=[]),
        }
        for label, cfg in bad.items():
            with self.subTest(label):
                self.dump(self.cfg, cfg)
                code, out = self.run_gate()
                self.assertEqual(code, 2, out)


class Playwright(GateCase):
    def report(self, file="a11y.spec.ts", config=True):
        cfg = {"rootDir": "@TREE@/tests/e2e", "projects": [
            {"name": "chromium", "testDir": "@TREE@/tests/e2e/dashboard"}]}
        spec = {"title": "has no violations", "file": file, "tests": [
            {"projectName": "chromium", "expectedStatus": "passed", "annotations": []}]}
        out = {"suites": [{"title": file, "file": file, "specs": [spec]}]}
        if config:
            out["config"] = cfg
        return json.dumps(out)

    def lister(self, payload):
        self.write("pw.json", payload)
        self.write("lister.py", "import os, sys\nsys.stdout.write(open('pw.json').read().replace('@TREE@', os.getcwd()))\n")
        cfg = dict(CONFIG, suites=[{"name": "pw", "cwd": ".", "cmd": ["python3", "lister.py"],
                                    "format": "playwright-json"}])
        self.dump(self.cfg, cfg)

    def test_ids_are_tree_relative_and_pass_the_source_check(self):
        self.write("tests/e2e/dashboard/a11y.spec.ts", "test('has no violations', async () => {});\n")
        self.lister(self.report())
        self.commit("base2")
        self.base_ref = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"], check=True,
                                       capture_output=True, text=True).stdout.strip()
        self.git("worktree", "remove", "--force", self.base_tree)
        self.git("worktree", "add", "-q", "--detach", self.base_tree, self.base_ref)
        self.write("note.txt", "x")
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)
        self.assertIn("suite pw: 0 of 1 unverifiable", out)
        rc = subprocess.run([sys.executable, str(CORE), "list", "--config", self.cfg, "--tree", self.repo],
                            capture_output=True, text=True)
        self.assertIn("pw::tests/e2e/dashboard/a11y.spec.ts::chromium::has no violations", rc.stdout)

    def test_deleted_playwright_source_with_forged_list_fails(self):
        self.write("tests/e2e/dashboard/a11y.spec.ts", "test('has no violations', async () => {});\n")
        self.lister(self.report())
        self.commit("base2")
        self.base_ref = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"], check=True,
                                       capture_output=True, text=True).stdout.strip()
        self.git("worktree", "remove", "--force", self.base_tree)
        self.git("worktree", "add", "-q", "--detach", self.base_tree, self.base_ref)
        self.write("tests/e2e/dashboard/a11y.spec.ts", "// emptied\n")
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 1, out)
        self.assertIn("not found in source", out)

    def test_unresolvable_file_is_2(self):
        self.lister(self.report(config=False))
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 2, out)

    def test_mostly_unverifiable_suite_is_2(self):
        # the lister lists ids whose files are not in the repo: the source check would be a no-op
        self.write("tests.jsonl", jl(*[("nofile%d.py::T.t" % i, False) for i in range(5)]))
        self.commit("base2")
        self.base_ref = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"], check=True,
                                       capture_output=True, text=True).stdout.strip()
        self.git("worktree", "remove", "--force", self.base_tree)
        self.git("worktree", "add", "-q", "--detach", self.base_tree, self.base_ref)
        self.write("note.txt", "x")
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 2, out)
        self.assertIn("source check covers too few ids", out)


class BadRecords(GateCase):
    def check(self, lines):
        self.write("tests.jsonl", lines)
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 2, out)

    def test_missing_skipped_is_2(self):
        self.check(json.dumps({"id": "a.py::T.one"}) + "\n")

    def test_non_bool_skipped_is_2(self):
        self.check(json.dumps({"id": "a.py::T.one", "skipped": "no"}) + "\n")

    def test_empty_id_is_2(self):
        self.check(json.dumps({"id": "", "skipped": False}) + "\n")

    def test_non_object_record_is_2(self):
        self.check('["a.py::T.one", false]\n')

    def test_bad_list_file_record_is_2(self):
        path = os.path.join(self.tmp, "bad.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"suite": "fake", "id": 5, "skipped": False}) + "\n")
        code, out = self.run_gate(extra=["--head-list", path])
        self.assertEqual(code, 2, out)


class Invalid(GateCase):
    def test_unresolved_base_is_2(self):
        code, out = self.run_gate(base_ref="no-such-ref")
        self.assertEqual(code, 2, out)

    def test_lister_crash_is_2(self):
        self.write("crash", "")
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 2, out)
        self.assertIn("lister exited 3", out)

    def test_empty_list_is_2(self):
        self.write("tests.jsonl", "")
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 2, out)
        self.assertIn("zero tests", out)

    def test_unparseable_list_is_2(self):
        self.write("garbage", "")
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 2, out)
        self.assertIn("unparseable", out)

    def test_bad_config_is_2(self):
        self.dump(self.cfg, {"suites": []})
        code, out = self.run_gate()
        self.assertEqual(code, 2, out)


class CoreToken(GateCase):
    def test_base_tree_without_core_is_listed_by_running_core(self):
        os.makedirs(os.path.join(self.tmp, "t", "tests"))
        with open(os.path.join(self.tmp, "t", "tests", "test_x.py"), "w", encoding="utf-8") as f:
            f.write("import unittest\nclass A(unittest.TestCase):\n    def test_a(self):\n        pass\n")
        cfg = dict(CONFIG, suites=[{"name": "u", "cwd": ".", "cmd": ["python3", "{core}", "list-unittest", "tests"],
                                    "format": "jsonl"}])
        path = os.path.join(self.tmp, "core-cfg.json")
        self.dump(path, cfg)
        tree = os.path.join(self.tmp, "t")
        self.assertFalse(os.path.exists(os.path.join(tree, "scripts", "test_integrity.py")))
        proc = subprocess.run([sys.executable, str(CORE), "list", "--config", path, "--tree", tree],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("u::tests/test_x.py::A.test_a", proc.stdout)


    def test_core_dir_token_points_beside_the_core(self):
        cfg = dict(CONFIG, suites=[{"name": "d", "cwd": ".", "format": "jsonl", "cmd": [
            "python3", "-c",
            "import json,os,sys;print(json.dumps({'id': str(os.path.exists(sys.argv[1] + '/test_integrity.py')), 'skipped': False}))",
            "{core_dir}"]}])
        path = os.path.join(self.tmp, "dir-cfg.json")
        self.dump(path, cfg)
        proc = subprocess.run([sys.executable, str(CORE), "list", "--config", path, "--tree", self.repo],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("d::True", proc.stdout)


class Formats(GateCase):
    def parse(self, fmt, payload):
        sys.path.insert(0, str(CORE.parent))
        try:
            import test_integrity as ti
        finally:
            sys.path.pop(0)
        fn = {"vitest-json": ti._parse_vitest, "playwright-json": ti._parse_playwright}[fmt]
        return fn(json.dumps(payload), "/repo")

    def test_vitest_ids_are_relative_to_tree(self):
        got = self.parse("vitest-json", [{"name": "a > b", "file": "/repo/web/x.test.ts"}])
        self.assertEqual(got, [("web/x.test.ts::a > b", False)])

    def test_playwright_ids_include_project_and_skip(self):
        payload = {"config": {"rootDir": "/repo", "projects": []},
                   "suites": [{"title": "x.spec.ts", "file": "x.spec.ts", "specs": [
            {"title": "t1", "file": "x.spec.ts", "tests": [
                {"projectName": "chromium", "expectedStatus": "passed", "annotations": []},
                {"projectName": "webkit", "expectedStatus": "skipped", "annotations": []}]}]}]}
        got = self.parse("playwright-json", payload)
        self.assertEqual(got, [("x.spec.ts::chromium::t1", False), ("x.spec.ts::webkit::t1", True)])

    def test_list_subcommand_writes_out_file(self):
        out = os.path.join(self.tmp, "out.jsonl")
        proc = subprocess.run([sys.executable, str(CORE), "list", "--config", self.cfg, "--tree", self.repo,
                               "--out", out], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(out, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f]
        self.assertEqual([r["id"] for r in rows], ["fake::a.py::T.one", "fake::a.py::T.two"])


if __name__ == "__main__":
    unittest.main()
