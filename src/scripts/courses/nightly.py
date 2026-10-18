"""The nightly course run is optional: pick its time, turn the schedule off, or run it now (`courses.py nightly`).

    nightly status [--json]
    nightly set --time HH:MM [--script P] [--label L]
    nightly off
    nightly run-now [--dry] [--script P]

On macOS the schedule is a LaunchAgent plist (an existing one is updated in place and backed up first). Elsewhere
`set` prints a cron line and writes nothing. Stdlib only, Python 3.9+; never reads the registry except for the
last run time and the log folder.
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_LABEL = "com.academic-writer.courses-daily"
SCRIPT_NAME = "courses-daily.sh"
EXAMPLE = "scripts/courses-daily.sh.example"
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
DISABLED = ".disabled"


def _agents_dir(args: argparse.Namespace) -> Path:
    return Path(args.launch_agents_dir) if args.launch_agents_dir else Path.home() / "Library" / "LaunchAgents"


def _default_script() -> Path:
    return Path.home() / ".academic-writer" / "bin" / SCRIPT_NAME


def _read_plist(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = plistlib.loads(path.read_bytes())
    except Exception:  # unreadable or not a plist
        return None
    return data if isinstance(data, dict) else None


def _script_of(data: Dict[str, Any]) -> Optional[str]:
    argv = [a for a in data.get("ProgramArguments") or [] if isinstance(a, str)]
    for arg in argv:
        if arg.endswith(SCRIPT_NAME):
            return arg
    return argv[-1] if len(argv) > 1 else None


def _time_of(data: Dict[str, Any]) -> Optional[str]:
    interval = data.get("StartCalendarInterval")
    if isinstance(interval, list):
        interval = interval[0] if interval else None
    if isinstance(interval, dict) and "Hour" in interval:
        try:
            return "%02d:%02d" % (int(interval["Hour"]), int(interval.get("Minute", 0)))
        except (TypeError, ValueError):
            return None
    return None


def find_plist(agents: Path, label: Optional[str]) -> Tuple[Optional[Path], Optional[Dict[str, Any]], bool]:
    """(path, data, disabled). Enabled plists win over a `.plist.disabled` one. Match by label, by a
    ProgramArguments entry ending courses-daily.sh, or by `*academic*.plist`."""
    try:
        listing = sorted(p for p in agents.iterdir() if p.is_file()) if agents.is_dir() else []
    except OSError:
        listing = []
    for disabled in (False, True):
        suffix = ".plist" + (DISABLED if disabled else "")
        candidates = [p for p in listing if p.name.endswith(suffix)]
        if label:
            for p in candidates:
                if p.name == label + suffix:
                    return p, _read_plist(p) or {}, disabled
        parsed = [(p, _read_plist(p)) for p in candidates]
        for p, data in parsed:
            if data and ((label and data.get("Label") == label) or
                         any(isinstance(a, str) and a.endswith(SCRIPT_NAME) for a in data.get("ProgramArguments") or [])):
                return p, data, disabled
        for p, data in parsed:
            if "academic" in p.name:
                return p, data or {}, disabled
    return None, None, False


def _label_of(path: Path, data: Dict[str, Any]) -> str:
    if isinstance(data.get("Label"), str) and data["Label"]:
        return data["Label"]
    name = path.name
    for suffix in (".plist" + DISABLED, ".plist"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _term_dir() -> Optional[Path]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I leaves the script dir off sys.path
    try:
        import dashboard
        return dashboard.resolve_directory(None)
    except Exception:
        return None


def _last_run() -> Optional[str]:
    directory = _term_dir()
    if directory is None:
        return None
    try:
        import dashboard
        return dashboard._nightly(directory)
    except Exception:
        return None


def _launchctl(args: argparse.Namespace, *argv: str) -> int:
    cmd = [args.launchctl or "launchctl", *argv]
    try:
        return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    except OSError:
        return 127


def _domain() -> str:
    return "gui/%d" % os.getuid()


def _status(args: argparse.Namespace) -> int:
    path, data, disabled = find_plist(_agents_dir(args), args.label) if args.platform == "darwin" else (None, None, False)
    data = data or {}
    state = {
        "scheduled": bool(path and not disabled and _time_of(data)),
        "time": None if disabled or not path else _time_of(data),
        "plist": str(path) if path else None,
        "script": _script_of(data) if path else None,
        "label": _label_of(path, data) if path else None,
        "last_run": _last_run(),
    }
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0
    if state["scheduled"]:
        print("Nightly run: every day at %s (%s)" % (state["time"], state["plist"]))
    elif disabled:
        print("Nightly run: off, runs on demand (`nightly run-now`). `nightly set --time HH:MM` turns it back on.")
    elif args.platform != "darwin":
        print("Nightly run: this computer is not macOS, so there is no managed schedule; `nightly set` prints a cron line.")
    else:
        print("Nightly run: not scheduled, runs on demand (`nightly run-now`). `nightly set --time HH:MM` schedules it.")
    if state["script"]:
        print("Script: %s" % state["script"])
    print("Last run: %s" % (state["last_run"] or "none yet"))
    return 0


def _resolve_script(args: argparse.Namespace, existing: Optional[Dict[str, Any]]) -> Tuple[Optional[Path], Optional[str]]:
    chosen = args.script or (_script_of(existing) if existing else None) or str(_default_script())
    path = Path(chosen).expanduser()
    if not path.is_file():
        return None, ("error: the nightly script %s does not exist. Copy %s from the plugin to %s, review it, "
                      "and run this again (or pass --script)." % (path, EXAMPLE, _default_script()))
    return path, None


def _backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = path.with_name("%s.bak-%s" % (path.name, stamp))
    n = 1
    while target.exists():
        target = path.with_name("%s.bak-%s-%d" % (path.name, stamp, n))
        n += 1
    shutil.copy2(path, target)
    return target


def _log_path() -> Path:
    directory = _term_dir()
    logs = (directory / "logs") if directory else Path.home() / ".academic-writer" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs / "launchd.log"


def _set(args: argparse.Namespace) -> int:
    match = TIME_RE.match(args.time or "")
    if not match:
        print("error: --time must be HH:MM on a 24-hour clock (for example 03:30), got %r" % (args.time,), file=sys.stderr)
        return 2
    hour, minute = int(match.group(1)), int(match.group(2))
    darwin = args.platform == "darwin"
    path, data, disabled = find_plist(_agents_dir(args), args.label) if darwin else (None, None, False)
    script, problem = _resolve_script(args, data)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    if not darwin:
        print("Not macOS: no schedule was written. Add this line to your crontab (crontab -e):")
        print("%d %d * * * bash %s" % (minute, hour, script))
        return 0
    agents = _agents_dir(args)
    label = args.label or (_label_of(path, data) if path else DEFAULT_LABEL)
    target = agents / (path.name[: -len(DISABLED)] if path and disabled else path.name) if path else agents / (label + ".plist")
    new: Dict[str, Any] = dict(data or {})
    env = dict(new.get("EnvironmentVariables") or {})
    if os.environ.get("ACADEMIC_HOME"):
        env["ACADEMIC_HOME"] = os.environ["ACADEMIC_HOME"]
    log = str(_log_path())
    new.update({"Label": label, "ProgramArguments": ["/bin/bash", str(script)],
                "StartCalendarInterval": {"Hour": hour, "Minute": minute}, "RunAtLoad": False,
                "StandardOutPath": log, "StandardErrorPath": log})
    if env:
        new["EnvironmentVariables"] = env
    agents.mkdir(parents=True, exist_ok=True)
    backup = _backup(path) if path and not disabled else None
    scratch = target.with_name(target.name + ".tmp")
    scratch.write_bytes(plistlib.dumps(new))
    os.replace(scratch, target)
    if path and disabled:
        path.unlink()
    if not args.no_load:
        _launchctl(args, "bootout", "%s/%s" % (_domain(), label))  # not loaded yet is fine
        code = _launchctl(args, "bootstrap", _domain(), str(target))
        if code != 0:
            print("warning: launchctl bootstrap exited %d; the plist is written, load it with: launchctl bootstrap %s %s"
                  % (code, _domain(), target), file=sys.stderr)
    print("Nightly run set for %02d:%02d every day (%s)." % (hour, minute, target))
    if backup:
        print("Previous plist saved as %s" % backup)
    return 0


def _off(args: argparse.Namespace) -> int:
    if args.platform != "darwin":
        print("Not macOS: remove the courses-daily line from your crontab (crontab -e). The nightly run now runs on demand: `nightly run-now`.")
        return 0
    path, data, disabled = find_plist(_agents_dir(args), args.label)
    if path is None or disabled:
        print("The nightly run is already off; it runs on demand (`nightly run-now`).")
        return 0
    label = _label_of(path, data or {})
    if not args.no_load:
        _launchctl(args, "bootout", "%s/%s" % (_domain(), label))
    os.replace(path, path.with_name(path.name + DISABLED))
    print("Nightly schedule off (%s kept as %s). It now runs on demand: `nightly run-now`. `nightly set --time HH:MM` turns it back on."
          % (path.name, path.name + DISABLED))
    return 0


def _run_now(args: argparse.Namespace) -> int:
    data = None
    if args.platform == "darwin":
        _, data, _ = find_plist(_agents_dir(args), args.label)
    script, problem = _resolve_script(args, data)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    env = dict(os.environ)
    for key, value in ((data or {}).get("EnvironmentVariables") or {}).items():
        if isinstance(key, str) and isinstance(value, str):
            env.setdefault(key, value)  # what launchd would pass; the caller's environment wins
    if args.dry:
        env["COURSES_DRY"] = "1"
    sys.stdout.flush()
    return subprocess.run(["bash", str(script)], env=env).returncode


def add_parser(sub) -> None:
    nightly = sub.add_parser("nightly", help="choose the nightly run time, turn the schedule off, or run it now")
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--launch-agents-dir", help="LaunchAgents folder (default ~/Library/LaunchAgents)")
    shared.add_argument("--launchctl", help="launchctl program to call (default launchctl)")
    shared.add_argument("--no-load", action="store_true", help="write or rename the plist without calling launchctl")
    shared.add_argument("--platform", default=sys.platform, help="darwin manages a LaunchAgent; anything else prints a cron line")
    shared.add_argument("--label", help="LaunchAgent label (default: the existing plist's, else %s)" % DEFAULT_LABEL)
    actions = nightly.add_subparsers(dest="nightly_command", required=True)
    st = actions.add_parser("status", parents=[shared], help="is the nightly run scheduled, and when did it last run")
    st.add_argument("--json", action="store_true")
    se = actions.add_parser("set", parents=[shared], help="schedule the nightly run at HH:MM every day")
    se.add_argument("--time", required=True, help="24-hour HH:MM, for example 03:30")
    se.add_argument("--script", help="the nightly script (default: the existing plist's, else ~/.academic-writer/bin/%s)" % SCRIPT_NAME)
    actions.add_parser("off", parents=[shared], help="turn the schedule off; the run is then on demand only")
    rn = actions.add_parser("run-now", parents=[shared], help="run the nightly script now, in the foreground")
    rn.add_argument("--script", help="the nightly script (default: the plist's, else ~/.academic-writer/bin/%s)" % SCRIPT_NAME)
    rn.add_argument("--dry", action="store_true", help="print the planned steps without running them (COURSES_DRY=1)")


def run(args: argparse.Namespace) -> int:
    handlers = {"status": _status, "set": _set, "off": _off, "run-now": _run_now}
    return handlers[args.nightly_command](args)
