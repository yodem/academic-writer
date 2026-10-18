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
IDS = ["home", "profile", "python", "python-addons", "hspell", "trove", "gemini-key",
       "notebooklm", "pageindex", "nightly-job"]


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
        return by_id(self.mod.run_checks(env or self.env, fake_which(which), run or fake_run(), platform))

    def test_ids_in_order(self):
        checks = self.mod.run_checks(self.env, fake_which({"python3": "/usr/bin/python3"}), fake_run(), "linux")
        self.assertEqual([c["id"] for c in checks], IDS)
        for c in checks:
            self.assertEqual(set(c), {"id", "label_he", "ok", "optional", "found", "required", "reason_he", "fix"})

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
        for cid in ("python", "trove", "hspell"):
            self.assertFalse(got[cid]["optional"], cid)

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
