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

    def run_gate(self, body=None, labels=None, events=None, base_ref=None):
        argv = [sys.executable, str(CORE), "run", "--config", self.cfg, "--base-tree", self.base_tree,
                "--head-tree", self.repo, "--base-ref", base_ref or self.base_ref]
        for flag, content, name in (("--pr-body-file", body, "body.txt"), ("--labels-file", labels, "labels.txt"),
                                    ("--label-events-file", events, "events.json")):
            if content is not None:
                path = os.path.join(self.tmp, name)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content if isinstance(content, str) else json.dumps(content))
                argv += [flag, path]
        proc = subprocess.run(argv, capture_output=True, text=True)
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
        self.write(".github/workflows/ci.yml", "name: x\n")
        self.commit("head")
        code, out = self.run_gate()
        self.assertEqual(code, 1)
        self.assertIn(".github/workflows/ci.yml", out)

    def test_guarded_path_with_maintainer_label_passes(self):
        self.write(".github/workflows/ci.yml", "name: x\n")
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
            "import json,os,sys;print(json.dumps({'id': str(os.path.exists(sys.argv[1] + '/test_integrity.py'))}))",
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
        payload = {"suites": [{"title": "x.spec.ts", "file": "x.spec.ts", "specs": [
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
