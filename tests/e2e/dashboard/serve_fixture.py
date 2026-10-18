"""Serve a named fixture home through DashboardServer with a fixed clock, for the Playwright e2e suite.

    python3 tests/e2e/dashboard/serve_fixture.py --fixture student --port 8765 --key K --now 2026-10-16T18:00:00+03:00

Prints `READY <url>` once listening and serves until killed.
"""
import argparse
import shutil
import signal
import sys
import tempfile
import threading
import types
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src" / "scripts" / "courses"))
sys.path.insert(0, str(ROOT / "tests" / "courses"))

import dashboard  # noqa: E402

FIXTURES = ("student", "lecturer", "empty", "home-unreachable", "python-missing")


class _PytestStub(types.ModuleType):
    """Just enough of pytest for test_dashboard to import: decorators pass the function through."""

    def __getattr__(self, name):
        def passthrough(*args, **kwargs):
            if len(args) == 1 and callable(args[0]) and not kwargs:
                return args[0]
            return passthrough

        return passthrough


def build_student(tmp: Path) -> Path:
    try:
        import pytest  # noqa: F401  (test_dashboard imports it at module level; make_reg itself does not use it)
    except ImportError:
        sys.modules["pytest"] = _PytestStub("pytest")
    from test_dashboard import make_reg  # today's make_reg data

    directory, *_ = make_reg(tmp)
    return directory


def build_empty(tmp: Path):
    return None


# Task 14 fills the other fixtures in; until then they serve the same data as `student` or nothing.
BUILDERS = {
    "student": build_student,
    "lecturer": build_student,
    "empty": build_empty,
    "home-unreachable": build_empty,
    "python-missing": build_empty,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True, choices=FIXTURES)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--key", required=True)
    ap.add_argument("--now", required=True, help="ISO timestamp the server clock is pinned to")
    args = ap.parse_args()

    now = datetime.fromisoformat(args.now)
    tmp = Path(tempfile.mkdtemp(prefix="aw-e2e-"))
    try:
        directory = BUILDERS[args.fixture](tmp)
        srv = dashboard.DashboardServer(lambda: directory, port=args.port, key=args.key, interval=0.2,
                                        now=lambda: now).start()
        print(f"READY {srv.url}", flush=True)
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        stop.wait()
        srv.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
