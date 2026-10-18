"""Rehearsal of the home migration on the layout a real Mac carries (all paths live under tmp_path).

A fake HOME holds the legacy registry (Hebrew term folder, absolute paths inside course and lesson JSON, docs that
name the folder as ~/ and absolute), the installed bin/ scripts, a LaunchAgents plist and a plugin data dir.
home_migrate.py runs as a subprocess, previewed and then applied; launchctl is never called.
"""
import hashlib
import json
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "scripts"))
import home  # noqa: E402

MIGRATE = ROOT / "src" / "scripts" / "home_migrate.py"
COURSES = ROOT / "src" / "scripts" / "courses" / "courses.py"
DAILY_EXAMPLE = ROOT / "scripts" / "courses-daily.sh.example"
TERM = "תשפ״ז"
SLUGS = ("cohen", "kane", "levi")
LABEL = "com.example.academic-courses-daily"


def tree(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class Mac:
    """The fake machine: HOME, the new home H, LaunchAgents, plugin data dir, external audio."""

    def __init__(self, base: Path):
        self.base = base
        self.hm = base / "fakehome"
        self.aw = self.hm / ".academic-writer"
        self.root = self.aw / "courses"          # the legacy registry root (migration default --legacy)
        self.term = self.root / TERM
        self.bin = self.aw / "bin"
        self.agents = self.hm / "Library" / "LaunchAgents"
        self.data = base / "plugin-data"
        self.new_home = base / "Academic"
        self.terms = self.new_home / ".academic-helper" / "terms"
        self.external = base / "external" / "rec.m4a"
        self.abs_prefix = str(self.root)
        self.build()

    def build(self) -> None:
        term, prefix = self.term, self.abs_prefix
        (term / "logs").mkdir(parents=True)
        (term / "queue" / "done").mkdir(parents=True)
        (term / "queue" / "sources" / "done").mkdir(parents=True)
        (term / "term.json").write_text(json.dumps({"term": TERM, "name": TERM}, ensure_ascii=False), encoding="utf-8")
        for slug in SLUGS:
            pdf = term / "sources" / slug / "x.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-1.4 " + slug.encode())
            course = {"slug": slug, "name": "קורס " + slug, "sources": [
                {"id": "s1", "file": str(pdf), "path": str(pdf), "title": "x"},
                {"id": "s2", "title": "no file yet"}]}
            (term / (slug + ".json")).write_text(json.dumps(course, ensure_ascii=False, indent=2), encoding="utf-8")
        for k in (1, 2):
            lesson = term / "lessons" / str(k)
            lesson.mkdir(parents=True)
            (lesson / "a.m4a").write_bytes(b"audio%d" % k)
            meta = {"lesson": k, "audio_path": str(lesson / "a.m4a")}
            (lesson / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        self.external.parent.mkdir(parents=True)
        self.external.write_bytes(b"external")
        ext_meta = term / "lessons" / "3"
        ext_meta.mkdir(parents=True)
        (ext_meta / "meta.json").write_text(json.dumps({"lesson": 3, "audio_path": str(self.external)}), encoding="utf-8")
        (term / "LEAD-HANDOFF.md").write_text(
            "# Handoff\nRegistry: ~/.academic-writer/courses/%s/\nAbsolute: %s/%s/term.json\nHome form: $HOME/.academic-writer/courses/%s\n"
            % (TERM, prefix, TERM, TERM), encoding="utf-8")
        (term / "logs" / "daily-2026-10-17.log").write_text("ran %s/%s\n" % (prefix, TERM), encoding="utf-8")
        (term / "queue" / "done" / "job1.json").write_text(json.dumps({"file": "%s/%s/a.pdf" % (prefix, TERM)}), encoding="utf-8")
        (term / "queue" / "sources" / "done" / "job2.json").write_text(json.dumps({"file": "%s/%s/b.pdf" % (prefix, TERM)}), encoding="utf-8")
        (term / "launchd.log").write_text("started %s/%s\n" % (prefix, TERM), encoding="utf-8")

        self.bin.mkdir(parents=True)
        example = DAILY_EXAMPLE.read_text(encoding="utf-8")
        legacy_term = 'TERM_DIR="${COURSES_TERM_DIR:-$HOME/.academic-writer/courses/%s}"' % TERM
        installed, n1 = re.subn(r'^export ACADEMIC_HOME=.*\n', "", example, flags=re.M)
        installed, n2 = re.subn(r'^TERM_DIR=.*$', lambda _m: legacy_term, installed, flags=re.M)
        assert (n1, n2) == (1, 1), "the example daily script changed shape; update the rehearsal"
        self.daily = self.bin / "courses-daily.sh"
        self.daily.write_text(installed, encoding="utf-8")
        self.sync = self.bin / "courses-sync-nanoclaw.sh"
        self.sync.write_text('#!/bin/bash\nSRC="$HOME/.academic-writer/courses/%s/"\necho "$SRC"\n' % TERM, encoding="utf-8")
        self.lock = self.bin / "book-lock.sh"
        self.lock.write_text('#!/bin/bash\nDIR="${COURSES_LOCK_DIR:-$HOME/.academic-writer/courses/%s/locks}"\nmkdir -p "$DIR"\n' % TERM,
                             encoding="utf-8")
        self.other = self.bin / "unrelated.sh"
        self.other.write_text("#!/bin/bash\necho hello\n", encoding="utf-8")

        self.agents.mkdir(parents=True)
        self.plist = self.agents / (LABEL + ".plist")
        self.plist.write_bytes(plistlib.dumps({
            "Label": LABEL, "ProgramArguments": ["/bin/bash", str(self.daily)],
            "StartCalendarInterval": {"Hour": 3, "Minute": 0},
            "StandardOutPath": "%s/%s/launchd.log" % (prefix, TERM),
            "StandardErrorPath": "%s/%s/launchd.log" % (prefix, TERM)}))
        self.other_plist = self.agents / "com.example.unrelated.plist"
        self.other_plist.write_bytes(plistlib.dumps({"Label": "com.example.unrelated", "ProgramArguments": ["/usr/bin/true"]}))
        self.data.mkdir()

    def env(self, **extra) -> dict:
        env = {k: v for k, v in os.environ.items()
               if k not in ("ACADEMIC_HOME", "CLAUDE_PLUGIN_DATA", "ACADEMIC_COURSES_DIR", "ACADEMIC_TERM", "COURSES_TERM_DIR")}
        env["HOME"] = str(self.hm)
        env.update(extra)
        return env

    def migrate(self, apply: bool) -> "tuple[subprocess.CompletedProcess, dict]":
        cmd = [sys.executable, "-I", str(MIGRATE), "--home", str(self.new_home), "--daily-script", str(self.daily),
               "--launch-agents-dir", str(self.agents), "--data-dir", str(self.data)]
        if apply:
            cmd.append("--apply")
        out = subprocess.run(cmd, env=self.env(), capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stdout + out.stderr
        return out, json.loads(out.stdout)

    def baks(self) -> set:
        found = set()
        for top in (self.base,):
            found.update(str(p) for p in top.rglob("*.bak-*"))
        return found

    def live_files(self):
        """Files a user or launchd reads: the new home, bin/, the plists. Not logs, done queues, backups, .migrated-*."""
        roots = [self.new_home, self.bin, self.agents]
        for root in roots:
            for p in sorted(root.rglob("*")):
                if not p.is_file():
                    continue
                rel = p.relative_to(self.base).parts
                if ".bak-" in p.name or p.suffix == ".log" or "logs" in rel or "done" in rel:
                    continue
                if any(part.startswith("courses.migrated-") for part in rel):
                    continue
                yield p


@pytest.fixture
def mac(tmp_path):
    return Mac(tmp_path)


def legacy_forms(mac: Mac) -> list:
    return [mac.abs_prefix, "~/.academic-writer/courses", "$HOME/.academic-writer/courses", "${HOME}/.academic-writer/courses"]


def test_preview_changes_nothing(mac):
    before = tree(mac.base)
    _out, plan = mac.migrate(apply=False)
    assert tree(mac.base) == before
    todo = {s["kind"] for s in plan["steps"] if s["status"] == "todo"}
    assert {"set-home-pointer", "copy-registry", "rewrite-registry", "daily-script", "helper-scripts", "launchd-plist"} <= todo
    assert not mac.new_home.exists() and not (mac.data / "home.json").exists()


def test_apply_fixes_the_whole_mac_layout(mac):
    originals = {str(p.relative_to(mac.term)): p.read_bytes() for p in mac.term.rglob("*")
                 if p.is_file() and ("logs" in p.relative_to(mac.term).parts or "done" in p.relative_to(mac.term).parts
                                     or p.suffix == ".log")}
    assert len(originals) == 4
    mac.migrate(apply=False)
    _out, plan = mac.migrate(apply=True)
    assert all(s["status"] == "done" for s in plan["steps"]), plan["steps"]

    # the pointer resolves to the new home
    assert home.home_dir({"CLAUDE_PLUGIN_DATA": str(mac.data)}) == mac.new_home

    # no legacy spelling is left in any live file
    for path in mac.live_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for form in legacy_forms(mac):
            assert form not in text, "%s still holds %s" % (path, form)

    # plist, sync, lock and daily were rewritten, each with a backup that is not named *.plist
    new_term = str(mac.terms)
    plist = plistlib.loads(mac.plist.read_bytes())
    assert plist["StandardOutPath"] == plist["StandardErrorPath"] == "%s/%s/launchd.log" % (new_term, TERM)
    assert plist["ProgramArguments"] == ["/bin/bash", str(mac.daily)]
    assert new_term in mac.sync.read_text(encoding="utf-8")
    daily = mac.daily.read_text(encoding="utf-8")
    assert 'export ACADEMIC_HOME="${ACADEMIC_HOME:-%s}"' % mac.new_home in daily
    for script in (mac.plist, mac.sync, mac.daily):
        backups = sorted(script.parent.glob(script.name + ".bak-*"))
        assert len(backups) == 1, script
        assert not backups[0].name.endswith(".plist")
    assert mac.other.read_text(encoding="utf-8") == "#!/bin/bash\necho hello\n"
    assert not list(mac.bin.glob("unrelated.sh.bak-*"))
    assert plistlib.loads(mac.other_plist.read_bytes())["Label"] == "com.example.unrelated"
    assert not list(mac.agents.glob("com.example.unrelated.plist.bak-*"))

    # every rewritten file path exists; the lessons audio moved with the registry
    new = mac.terms / TERM
    for slug in SLUGS:
        course = json.loads((new / (slug + ".json")).read_text(encoding="utf-8"))
        with_file = [s for s in course["sources"] if "file" in s]
        assert len(with_file) == 1
        for source in with_file:
            assert source["file"] == source["path"] == str(new / "sources" / slug / "x.pdf")
            assert Path(source["file"]).is_file()
    for k in (1, 2):
        audio = json.loads((new / "lessons" / str(k) / "meta.json").read_text(encoding="utf-8"))["audio_path"]
        assert audio == str(new / "lessons" / str(k) / "a.m4a") and Path(audio).is_file()
    # outside the registry, and the history, stay as they were
    assert json.loads((new / "lessons" / "3" / "meta.json").read_text(encoding="utf-8"))["audio_path"] == str(mac.external)
    for rel, data in originals.items():
        assert (new / rel).read_bytes() == data, rel
    handoff = (new / "LEAD-HANDOFF.md").read_text(encoding="utf-8")
    assert str(mac.terms) in handoff and "$HOME/.academic-writer" not in handoff

    # the registry loads the Hebrew term from the new home
    probe = ("import sys; sys.path.insert(0, %r); import courses, json; d = courses.registry_dir(%r); "
             "r = courses.Registry(d); print(json.dumps({'dir': str(d), 'term': r.term, 'slugs': sorted(r.courses)}, ensure_ascii=False))"
             % (str(COURSES.parent), TERM))
    out = subprocess.run([sys.executable, "-c", probe], env=mac.env(ACADEMIC_HOME=str(mac.new_home)),
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    loaded = json.loads(out.stdout)
    assert loaded["dir"] == str(new) and loaded["term"]["term"] == TERM
    assert loaded["slugs"] == sorted(SLUGS)


def test_lock_script_default_after_colon_dash_is_rewritten(mac):
    mac.migrate(apply=True)
    text = mac.lock.read_text(encoding="utf-8")
    assert "$HOME/.academic-writer/courses" not in text
    assert "%s/%s/locks" % (mac.terms, TERM) in text
    backups = sorted(mac.lock.parent.glob(mac.lock.name + ".bak-*"))
    assert len(backups) == 1


def test_second_apply_changes_nothing(mac):
    mac.migrate(apply=True)
    before, baks = tree(mac.base), mac.baks()
    assert baks
    out, plan = mac.migrate(apply=True)
    assert out.returncode == 0
    assert [s["status"] for s in plan["steps"]] and all(s["status"] == "done" for s in plan["steps"]), plan["steps"]
    assert mac.baks() == baks
    assert tree(mac.base) == before


def test_preview_after_migration_reports_everything_done(mac):
    """The user's hand-fixed state: migrated, nothing edited since. A preview has nothing left to do."""
    mac.migrate(apply=True)
    before = tree(mac.base)
    _out, plan = mac.migrate(apply=False)
    assert plan["steps"] and all(s["status"] == "done" for s in plan["steps"]), plan["steps"]
    assert plan["reload"] == []
    assert tree(mac.base) == before


def test_migrated_daily_script_dry_run_exits_zero(mac):
    mac.migrate(apply=True)
    logs_before = tree(mac.terms / TERM / "logs")
    stubs = mac.base / "stubs"
    stubs.mkdir()
    pgrep = stubs / "pgrep"
    pgrep.write_text("#!/bin/sh\nexit 1\n")
    pgrep.chmod(0o755)
    env = mac.env(ACADEMIC_HOME=str(mac.new_home), COURSES_DRY="1", PATH="%s:%s" % (stubs, os.environ["PATH"]))
    out = subprocess.run(["bash", str(mac.daily)], env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    plans = [line for line in out.stdout.splitlines() if line.startswith("PLAN: ")]
    assert any("courses.py daily" in p for p in plans)
    assert any(str(mac.terms / TERM) in p for p in plans if "fetch-queue" in p)
    assert tree(mac.terms / TERM / "logs") == logs_before  # a dry run writes no log
