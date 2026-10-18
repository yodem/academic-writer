"""Serve a named fixture home through DashboardServer with a fixed clock, for the Playwright e2e suite.

    python3 tests/e2e/dashboard/serve_fixture.py --fixture student --port 8765 --key K --now 2026-10-16T18:00:00+03:00
        [--workdir DIR]

Prints `READY <url>` once listening and serves until killed. With --workdir the fixture is rebuilt in that
folder (so specs can edit its files); without it a temp folder is used and removed on exit.

Fixtures (all deterministic: fixed clock, fixed setup checks, activity timestamps shifted to --now):
  student           student role, term registry, three workspaces (one run in progress, two done), one moved folder
  lecturer          lecturer role, no courses, teaching/project workspaces (runs + recently added sources)
  empty             no home folder chosen, no registry
  home-unreachable  home pointer names a folder that is gone
  python-missing    student home, Python not installed (setup incomplete)
"""
import argparse
import json
import os
import shutil
import signal
import sys
import time
import tempfile
import threading
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src" / "scripts" / "courses"))
sys.path.insert(0, str(ROOT / "src" / "scripts"))
sys.path.insert(0, str(ROOT / "tests" / "courses"))

import dashboard  # noqa: E402
import setup_checks  # noqa: E402

FIXTURES = ("student", "lecturer", "empty", "home-unreachable", "python-missing")
ACTIVITY = ROOT / "tests" / "fixtures" / "activity"
LONG_COURSE = "מבוא לפרשנות המקרא בימי הביניים (BIBL-204) — סמינר מתקדם בהנחיית ד״ר כהן"
LONG_FOLDER = "עבודה-סמינריונית-פרשנות-ימי-הביניים-BIBL-204-final-draft-v3"


class _PytestStub(types.ModuleType):
    """Just enough of pytest for test_dashboard to import: decorators pass the function through."""

    def __getattr__(self, name):
        def passthrough(*args, **kwargs):
            if len(args) == 1 and callable(args[0]) and not kwargs:
                return args[0]
            return passthrough

        return passthrough


def _registry(tmp: Path) -> Path:
    try:
        import pytest  # noqa: F401  (test_dashboard imports it at module level; make_reg itself does not use it)
    except ImportError:
        sys.modules["pytest"] = _PytestStub("pytest")
    from test_dashboard import make_reg  # today's make_reg data

    directory, *_ = make_reg(tmp)
    alpha = directory / "alpha.json"
    data = json.loads(alpha.read_text(encoding="utf-8"))
    data["name"] = LONG_COURSE  # a 40+ character Hebrew name with a Latin code, for the 360 px overflow check
    alpha.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return directory


def _shift(src: Path, dest: Path, start: datetime) -> None:
    """Copy an activity file with every `ts` moved so the first event is at `start`."""
    rows = [json.loads(ln) for ln in src.read_text(encoding="utf-8").splitlines() if ln.strip()]
    first = datetime.fromisoformat(rows[0]["ts"].replace("Z", "+00:00"))
    delta = start.astimezone(timezone.utc) - first
    out = []
    for row in rows:
        moment = datetime.fromisoformat(row["ts"].replace("Z", "+00:00")) + delta
        row["ts"] = moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"
        out.append(json.dumps(row, ensure_ascii=False))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(out) + "\n", encoding="utf-8")


def _home(tmp: Path, role: str, name: str) -> Path:
    home = tmp / "home"
    meta = home / ".academic-helper"
    meta.mkdir(parents=True)
    (meta / "home.md").write_text(f"---\nname: {name}\nrole: {role}\ninstitution: בר-אילן\ndegree: MA\ntargetLanguage: Hebrew\n---\n",
                                  encoding="utf-8")
    (meta / "workspaces.json").write_text("[]", encoding="utf-8")
    return home


def _register(home: Path, path: Path, wtype: str, course=None) -> None:
    rows_path = home / ".academic-helper" / "workspaces.json"
    rows = json.loads(rows_path.read_text(encoding="utf-8"))
    rows.append({"path": str(path), "type": wtype, "course": course, "term": None, "created": "2026-10-01T00:00:00Z"})
    rows_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def _workspace(tmp: Path, home: Path, folder: str, wtype: str, run: str, source: str, start: datetime,
               course=None, profile: bool = False) -> Path:
    ws = tmp / "ws" / folder
    _shift(ACTIVITY / source, ws / ".academic-helper" / "runs" / run / "activity.jsonl", start)
    if profile:
        (ws / ".academic-helper" / "profile.md").write_text("---\nworkspace_type: project\n---\n", encoding="utf-8")
    _register(home, ws, wtype, course)
    return ws


def _checks(tmp: Path, home, project, python: bool = True):
    """The real setup_checks.run_checks on a fake machine: every tool present, Python present or not."""
    env = {"HOME": str(tmp / "machine"), "CLAUDE_PROJECT_DIR": str(project or tmp / "none")}
    if home is not None:
        env["ACADEMIC_HOME"] = str(home)

    def which(cmd):
        if cmd in ("python3", "python"):
            return "/usr/bin/python3" if python else None
        return None if cmd in ("nlm", "pilib") else f"/usr/bin/{cmd}"

    def run(cmd):
        return (0, "ALL_PRESENT") if "-c" in cmd else (0, "Python 3.12.1")

    return lambda: setup_checks.run_checks(env, which=which, run=run, platform="linux")


class Built:
    def __init__(self, directory, home, setup):
        self.directory, self.home, self.setup = directory, home, setup


def build_student(tmp: Path, now: datetime, python: bool = True, home_gone: bool = False) -> Built:
    directory = _registry(tmp)
    home = _home(tmp, "student", "דנה")
    live = _workspace(tmp, home, LONG_FOLDER, "course", "run-live", "in-progress.jsonl",
                      now - timedelta(minutes=10), course="alpha", profile=True)
    _workspace(tmp, home, "thesis-proposal", "project", "run-0924", "done.jsonl", now - timedelta(days=2))
    _workspace(tmp, home, "book-review", "project", "run-0911", "done.jsonl", now - timedelta(days=6, hours=3))
    _register(home, tmp / "ws" / "moved-away", "project")  # a moved folder: shown "not found", never dropped
    if home_gone:
        gone = tmp / "moved-home"
        return Built(directory, gone, _checks(tmp, gone, live, python))
    return Built(directory, home, _checks(tmp, home, live, python))


def build_lecturer(tmp: Path, now: datetime) -> Built:
    home = _home(tmp, "lecturer", "ד״ר כהן")
    live = _workspace(tmp, home, "lecture-notes-2027", "teaching", "run-live", "in-progress.jsonl",
                      now - timedelta(minutes=10), profile=True)
    _workspace(tmp, home, "journal-article", "project", "run-0920", "done.jsonl", now - timedelta(days=3))
    _workspace(tmp, home, "conference-paper", "project", "run-0907", "done.jsonl", now - timedelta(days=9))
    added = (now - timedelta(days=2)).isoformat()
    (live / ".academic-helper" / "sources.json").write_text(json.dumps({"sources": [
        {"id": "s1", "title": "Commentary on Genesis, critical edition", "addedAt": added},
        {"id": "s2", "title": "פרשנות הרמב״ן לתורה", "addedAt": added},
        {"id": "s3", "title": "An old source", "addedAt": "2026-01-01T00:00:00+02:00"},
    ]}, ensure_ascii=False), encoding="utf-8")
    return Built(None, home, _checks(tmp, home, live))


def build_empty(tmp: Path, now: datetime) -> Built:
    return Built(None, None, _checks(tmp, None, None))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True, choices=FIXTURES)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--key", required=True)
    ap.add_argument("--now", required=True, help="ISO timestamp the server clock is pinned to")
    ap.add_argument("--workdir", help="build the fixture here (wiped first) and keep it after exit")
    args = ap.parse_args()

    now = datetime.fromisoformat(args.now)
    if args.workdir:
        tmp = Path(args.workdir).resolve()
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
    else:
        tmp = Path(tempfile.mkdtemp(prefix="aw-e2e-"))
    os.environ["ACADEMIC_COURSES_DIR"] = str(tmp / "root")
    try:
        name = args.fixture
        if name == "student":
            built = build_student(tmp, now)
        elif name == "python-missing":
            built = build_student(tmp, now, python=False)
        elif name == "home-unreachable":
            built = build_student(tmp, now, home_gone=True)
        elif name == "lecturer":
            built = build_lecturer(tmp, now)
        else:
            built = build_empty(tmp, now)
        # A port from the previous run can sit in TIME-WAIT for about a minute, and the dashboard does not reuse
        # addresses (on purpose: it moves to a free port instead). The suite needs fixed ports, so wait it out.
        deadline = time.monotonic() + 75
        while True:
            srv = dashboard.DashboardServer(lambda: built.directory, port=args.port, key=args.key, interval=0.2,
                                            now=lambda: now, home=lambda: built.home, setup=built.setup).start()
            if not args.port or srv.port == args.port or time.monotonic() > deadline:
                break
            srv.close()
            time.sleep(1)
        if args.port and srv.port != args.port:  # DashboardServer quietly takes a free port when the asked one is busy
            print(f"error: port {args.port} is busy (another e2e run?); set AW_E2E_PORT_BASE", file=sys.stderr, flush=True)
            srv.close()
            return 1
        print(f"READY {srv.url}", flush=True)
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        stop.wait()
        srv.close()
    finally:
        if not args.workdir:
            shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
