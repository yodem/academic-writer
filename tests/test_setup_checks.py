"""setup_checks.py: one deterministic source for health, setup and the dashboard."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "src" / "scripts" / "setup_checks.py"
SECRET = "AIza-super-secret-value-12345"
IDS = ["home", "profile", "git", "node", "python", "python-addons", "hspell", "gemini-key", "drive",
       "notebooklm", "trove", "kotar", "moodle", "pageindex", "nightly-job"]


def load():
    spec = importlib.util.spec_from_file_location("setup_checks", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["setup_checks"] = mod
    spec.loader.exec_module(mod)
    return mod


def by_id(checks):
    return {c["id"]: c for c in checks}


def fake_which(found):
    return lambda name: found.get(name)


def fake_run(version="Python 3.12.1", addons="ALL_PRESENT"):
    def run(cmd):
        if "--version" in cmd:
            return 0, version
        if "-c" in cmd:
            return 0, addons
        return 0, ""
    return run


class SetupChecks(unittest.TestCase):
    def setUp(self):
        self.mod = load()
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.env = {"HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.home / "proj")}

    def tearDown(self):
        self.tmp.cleanup()

    def run_checks(self, which=None, run=None, platform="linux", env=None):
        which = which if which is not None else {"python3": "/usr/bin/python3"}
        return by_id(self.mod.run_checks(env or self.env, fake_which(which), run or fake_run(), platform,
                                         exists=lambda p: False))

    def test_ids_in_order(self):
        checks = self.mod.run_checks(self.env, fake_which({"python3": "/usr/bin/python3"}), fake_run(), "linux")
        self.assertEqual([c["id"] for c in checks], IDS)
        for c in checks:
            self.assertEqual(set(c), {"id", "label_he", "ok", "optional", "found", "required", "reason_he", "fix",
                                      "fix_windows", "fix_mac"})
            self.assertTrue(c["fix_windows"] and c["fix_mac"], c["id"])

    def test_python_too_old(self):
        c = self.run_checks(run=fake_run(version="Python 3.8.10"))["python"]
        self.assertIs(c["ok"], False)
        self.assertEqual(c["found"], "3.8.10")
        self.assertEqual(c["required"], "3.9")
        self.assertIn("3.9", c["reason_he"])
        self.assertTrue(c["fix"])

    def test_python_ok(self):
        c = self.run_checks()["python"]
        self.assertIs(c["ok"], True)
        self.assertEqual(c["found"], "3.12.1")

    def test_python_store_stub_is_skipped_and_python_is_taken(self):
        def run(cmd):
            if cmd[0] == "C:/stub/python3.exe":  # the Microsoft Store alias: fails and prints no version
                return 9009, "Python was not found; run without arguments to install from the Microsoft Store"
            if "--version" in cmd:
                return 0, "Python 3.12.4"
            return 0, "ALL_PRESENT"
        got = self.run_checks(which={"python3": "C:/stub/python3.exe", "python": "C:/py/python.exe"}, run=run)
        self.assertIs(got["python"]["ok"], True)
        self.assertEqual(got["python"]["found"], "3.12.4")
        self.assertIs(got["python-addons"]["ok"], True)

    def test_python_py_launcher_is_the_last_resort(self):
        seen = []

        def run(cmd):
            seen.append(cmd)
            return (0, "Python 3.11.9") if cmd[:2] == ["C:/py.exe", "-3"] else (1, "")
        got = self.run_checks(which={"py": "C:/py.exe"}, run=run)
        self.assertIs(got["python"]["ok"], True)
        self.assertEqual(seen[0], ["C:/py.exe", "-3", "--version"])

    def test_python_2_does_not_count(self):
        got = self.run_checks(run=fake_run(version="Python 2.7.18"))["python"]
        self.assertIs(got["ok"], False)

    def test_python_only_a_store_stub_says_so(self):
        got = self.run_checks(which={"python": "C:/stub/python.exe"}, run=lambda cmd: (9009, "Python was not found"))
        self.assertIs(got["python"]["ok"], False)
        self.assertIn("Store", got["python"]["reason_he"])

    def test_git_and_node_rows(self):
        got = self.run_checks(which={"python3": "/usr/bin/python3"})
        for cid in ("git", "node"):
            self.assertIs(got[cid]["ok"], False)
            self.assertFalse(got[cid]["optional"])
        self.assertIn("winget install --id Git.Git", got["git"]["fix_windows"])
        self.assertIn("winget install --id OpenJS.NodeJS.LTS", got["node"]["fix_windows"])
        got = self.run_checks(which={"python3": "/usr/bin/python3", "git": "/usr/bin/git", "node": "/usr/bin/node"},
                              run=lambda cmd: (0, "v22.1.0") if cmd[0].endswith("node") else fake_run()(cmd))
        self.assertIs(got["git"]["ok"], True)
        self.assertIs(got["node"]["ok"], True)
        self.assertEqual(got["node"]["found"], "v22.1.0")

    def test_node_too_old(self):
        got = self.run_checks(which={"python3": "/usr/bin/python3", "node": "/usr/bin/node"},
                              run=lambda cmd: (0, "v16.20.0") if cmd[0].endswith("node") else fake_run()(cmd))
        self.assertIs(got["node"]["ok"], False)

    def test_node_version_command_fails_or_is_unreadable(self):
        for result in ((1, "boom"), (0, "not a version"), (0, "")):
            got = self.run_checks(which={"python3": "/usr/bin/python3", "node": "/usr/bin/node"},
                                  run=lambda cmd, result=result: result if cmd[0].endswith("node") else fake_run()(cmd))
            self.assertIs(got["node"]["ok"], False, result)
            self.assertIn("/usr/bin/node", got["node"]["reason_he"])
            self.assertIn("winget install --id OpenJS.NodeJS.LTS", got["node"]["fix_windows"])

    def test_drive_and_moodle_are_manual(self):
        got = self.run_checks()
        for cid in ("drive", "moodle"):
            self.assertIsNone(got[cid]["ok"])  # no script can see the Claude connector or a browser sign-in
            self.assertTrue(got[cid]["optional"])
        self.assertIn("10166901", got["drive"]["fix_windows"])
        self.assertIn("Connectors", got["drive"]["fix_mac"])

    def test_kotar_needs_chrome(self):
        self.assertIs(self.run_checks(platform="win32")["kotar"]["ok"], False)
        env = dict(self.env, ProgramFiles="C:\\Program Files")
        seen = []

        def exists(path):
            seen.append(path)
            return path.endswith("chrome.exe")
        checks = by_id(self.mod.run_checks(env, fake_which({"python3": "/usr/bin/python3"}), fake_run(), "win32",
                                           exists=exists))
        self.assertIs(checks["kotar"]["ok"], True)
        self.assertTrue(checks["kotar"]["optional"])
        mac = by_id(self.mod.run_checks(self.env, fake_which({"python3": "/usr/bin/python3"}), fake_run(), "darwin",
                                        exists=lambda p: p == "/Applications/Google Chrome.app"))
        self.assertIs(mac["kotar"]["ok"], True)

    def test_python_missing(self):
        got = self.run_checks(which={})
        self.assertIs(got["python"]["ok"], False)
        self.assertIsNone(got["python"]["found"])
        self.assertTrue(got["python"]["reason_he"])
        self.assertIsNone(got["python-addons"]["ok"])  # cannot probe without an interpreter

    def test_addons_missing_listed(self):
        c = self.run_checks(run=fake_run(addons="MISSING:lxml,pymupdf"))["python-addons"]
        self.assertIs(c["ok"], False)
        self.assertIn("lxml", c["reason_he"])
        self.assertIn("pymupdf", c["reason_he"])
        self.assertNotIn("pdfplumber", c["reason_he"])

    def test_nightly_not_applicable_on_linux(self):
        c = self.run_checks(platform="linux")["nightly-job"]
        self.assertIsNone(c["ok"])
        self.assertEqual(c["reason_he"], "רק ב-macOS")

    def test_optional_flags(self):
        got = self.run_checks()
        for cid in ("gemini-key", "notebooklm", "pageindex"):
            self.assertTrue(got[cid]["optional"], cid)
        self.assertFalse(got["python"]["optional"])
        self.assertTrue(got["trove"]["optional"])
        self.assertTrue(got["hspell"]["optional"])  # no profile language: not required

    def _profile(self, language, where="proj"):
        d = self.home / where / ".academic-helper"
        d.mkdir(parents=True, exist_ok=True)
        (d / "profile.md").write_text("---\ntargetLanguage: %s\n---\n" % language, encoding="utf-8")

    def test_hspell_required_only_for_hebrew(self):
        self._profile("he")
        c = self.run_checks()["hspell"]
        self.assertFalse(c["optional"])
        self.assertIs(c["ok"], False)
        self._profile("English")
        c = self.run_checks()["hspell"]
        self.assertTrue(c["optional"])

    def test_hspell_language_from_home_when_profile_lacks_it(self):
        hh = self.home / "h" / ".academic-helper"
        hh.mkdir(parents=True)
        (hh / "home.md").write_text("---\ntargetLanguage: Hebrew\n---\n", encoding="utf-8")
        env = dict(self.env, ACADEMIC_HOME=str(self.home / "h"))
        self.assertFalse(self.run_checks(env=env)["hspell"]["optional"])

    def test_trove_optional_with_plain_reason(self):
        c = self.run_checks()["trove"]
        self.assertTrue(c["optional"])
        self.assertIs(c["ok"], False)
        self.assertIn("Trove", c["reason_he"])
        self.assertGreater(len(c["reason_he"]), len("Trove לא מותקן"))

    def test_profile_without_workspace_context_is_not_a_failure(self):
        cwd = self.home / "elsewhere"
        cwd.mkdir()
        env = {"HOME": str(self.home)}
        checks = self.mod.run_checks(env, fake_which({"python3": "/usr/bin/python3"}), fake_run(), "linux",
                                     cwd=str(cwd))
        c = by_id(checks)["profile"]
        self.assertIsNone(c["ok"])
        self.assertTrue(c["reason_he"])
        # a profile in the working folder still counts
        (cwd / ".academic-helper").mkdir()
        (cwd / ".academic-helper" / "profile.md").write_text("---\nname: X\n---\n", encoding="utf-8")
        checks = self.mod.run_checks(env, fake_which({"python3": "/usr/bin/python3"}), fake_run(), "linux",
                                     cwd=str(cwd))
        self.assertIs(by_id(checks)["profile"]["ok"], True)

    def test_profile_ignores_pwd_env_and_uses_cwd(self):
        env = {"HOME": str(self.home), "PWD": str(self.home / "stale")}
        checks = self.mod.run_checks(env, fake_which({"python3": "/usr/bin/python3"}), fake_run(), "linux",
                                     cwd=str(self.home))
        self.assertIsNone(by_id(checks)["profile"]["ok"])

    def test_key_value_never_in_output(self):
        env = dict(self.env, GOOGLE_API_KEY=SECRET)
        checks = self.mod.run_checks(env, fake_which({"python3": "/usr/bin/python3"}), fake_run(), "linux")
        self.assertIs(by_id(checks)["gemini-key"]["ok"], True)
        self.assertNotIn(SECRET, json.dumps(checks, ensure_ascii=False))
        proc = subprocess.run([sys.executable, str(SCRIPT), "--json"], env={**env, "PATH": "/usr/bin:/bin"},
                              capture_output=True, text=True)
        self.assertNotIn(SECRET, proc.stdout + proc.stderr)

    def test_no_key_flags_only_optional(self):
        c = self.run_checks()["gemini-key"]
        self.assertIs(c["ok"], False)
        self.assertTrue(c["optional"])

    def test_home_and_profile(self):
        got = self.run_checks()
        self.assertIs(got["home"]["ok"], False)
        self.assertIs(got["profile"]["ok"], False)
        proj = self.home / "proj" / ".academic-helper"
        proj.mkdir(parents=True)
        (proj / "profile.md").write_text("---\nname: X\n---\n", encoding="utf-8")
        hh = self.home / "h" / ".academic-helper"
        hh.mkdir(parents=True)
        (hh / "home.md").write_text("---\nname: X\nrole: student\n---\n", encoding="utf-8")
        env = dict(self.env, ACADEMIC_HOME=str(self.home / "h"))
        got = self.run_checks(env=env)
        self.assertIs(got["home"]["ok"], True)
        self.assertIs(got["profile"]["ok"], True)

    def test_no_writes(self):
        def digest():
            h = hashlib.sha256()
            for p in sorted(self.home.rglob("*")):
                h.update(str(p.relative_to(self.home)).encode())
                if p.is_file():
                    h.update(p.read_bytes())
            return h.hexdigest()
        (self.home / "proj").mkdir()
        before = digest()
        self.run_checks(platform="darwin")
        self.run_checks(platform="linux")
        self.assertEqual(before, digest())

    def test_cli_json(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), "--json"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual([c["id"] for c in json.loads(proc.stdout)], IDS)


if __name__ == "__main__":
    unittest.main()
