#!/usr/bin/env python3
"""Reader for the agent-activity record (`runs/<id>/activity.jsonl`), stdlib only, Python 3.9.

`aw` and the plugin hooks append one JSON event per line (schema: schemas/activity-event.schema.json).
This module turns a run folder into a `RunView` for the dashboard's Writing page and lists runs across
workspaces. It never writes, never calls a model, and never raises on a bad line: a line that is torn
(a run killed mid-write) or not an event is skipped and counted in `unreadable`.

    python3 activity.py list --workspaces <workspaces.json> [--limit N]
    python3 activity.py show <path/to/activity.jsonl>
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_ACTIVE_RUN_MAX_AGE_MINUTES = 360

# Fixed step order per flow (mirrors FLOW_STEPS in src/cli/src/activity.ts and src/mod/model.ts; a test keeps the three equal).
FLOW_STEPS: Dict[str, List[str]] = {
    "write": ["outline", "draft", "audit", "redraft", "synthesize", "word"],
    "proofread": ["find", "verify", "memo", "apply"],
    "revise": ["read", "update-draft", "update-stores"],
    "edit": ["edit"],
    "edit-section": ["edit"],
}
# `outline` is finished by the skill before the first `aw` event of a write run.
IMPLICIT_DONE = {"outline"}

RunView = Dict[str, Any]


def _max_age_minutes() -> int:
    here = Path(__file__).resolve().parent
    for candidate in (here.parent / "thresholds.json", here.parent.parent / "thresholds.json"):
        try:
            value = json.loads(candidate.read_text(encoding="utf-8")).get("activity", {}).get("activeRunMaxAgeMinutes")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    return DEFAULT_ACTIVE_RUN_MAX_AGE_MINUTES


def _parse_ts(value: Any) -> Optional[float]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _read_events(path: Path) -> "tuple[List[Dict[str, Any]], int]":
    events: List[Dict[str, Any]] = []
    unreadable = 0
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return events, unreadable
    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            unreadable += 1
            continue
        if isinstance(row, dict) and isinstance(row.get("kind"), str):
            events.append(row)
        else:
            unreadable += 1
    return events, unreadable


def _usage(run_dir: Path) -> "tuple[Optional[int], Optional[float]]":
    """(tokens, cost_usd) summed from usage.jsonl; None for a field when any row has it null, or no file."""
    path = run_dir / "usage.jsonl"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None, None
    tokens: Optional[int] = 0
    cost: Optional[float] = 0.0
    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        tin, tout = row.get("input_tokens"), row.get("output_tokens")
        if tokens is not None:
            tokens = tokens + tin + tout if isinstance(tin, int) and isinstance(tout, int) else None
        c = row.get("cost_usd")
        if cost is not None:
            cost = cost + float(c) if isinstance(c, (int, float)) and not isinstance(c, bool) else None
    return tokens, (round(cost, 6) if cost is not None else None)


def _steps(flow: str, events: List[Dict[str, Any]], ended: bool, exit_ok: bool = False) -> List[Dict[str, str]]:
    order = FLOW_STEPS.get(flow)
    if order is None:
        return []
    seen_order: List[str] = []
    finished = set()
    for e in events:
        step = e.get("step")
        if not isinstance(step, str) or step not in order:
            continue
        if step not in seen_order:
            seen_order.append(step)
        if e["kind"] == "step_end":
            finished.add(step)
    last_seen = max((order.index(s) for s in seen_order), default=-1)
    result = []
    for index, step in enumerate(order):
        if step in finished:
            state = "done"
        elif step in seen_order:
            # Started, not ended: current while it is the furthest step reached and the run is open.
            state = "done" if index < last_seen else ("unknown" if ended else "current")
        elif step in IMPLICIT_DONE and last_seen > index:
            state = "done"
        elif ended and exit_ok:
            # Never happened in a run that finished well (e.g. no redraft was needed): skipped, not still to do.
            state = "skipped"
        else:
            state = "todo"
        result.append({"id": step, "state": state})
    return result


def _units(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    units: Dict[str, Dict[str, Any]] = {}
    for e in events:
        unit = e.get("unit")
        if not isinstance(unit, str):
            continue
        row = units.setdefault(unit, {"id": unit, "state": "unknown"})
        kind = e["kind"]
        if kind == "unit_drafted":
            # `aw draft` emits `redraft` then `unit_drafted` for a redo: the unit stays "redrafted".
            row["state"] = "redrafted" if row.get("_redo") else "drafted"
            row.pop("reason", None)
        elif kind == "redraft":
            row["_redo"] = True
            row["state"] = "redrafted"
            row.pop("reason", None)
        elif kind == "gate" and e.get("ok") is False:
            row["state"] = "rejected"
            if e.get("reason"):
                row["reason"] = e["reason"]
        elif kind == "audit_verdict":
            # A rejected paragraph keeps its unit rejected until the unit is drafted again; a verdict that
            # could not be read leaves a unit that is already passed or rejected as it is.
            verdict = e.get("verdict")
            if verdict == "PASS":
                if row["state"] != "rejected":
                    row["state"] = "passed"
            elif verdict in ("FAIL", "PARTIAL"):
                row["state"] = "rejected"
                if e.get("reason"):
                    row["reason"] = e["reason"]
            elif row["state"] not in ("passed", "rejected"):
                row["state"] = "unknown"
    for row in units.values():
        row.pop("_redo", None)
    return list(units.values())


def read_run(path: Path, workspace: Optional[str] = None, course: Optional[str] = None,
             now: Optional[float] = None) -> RunView:
    """The view of one run from its `activity.jsonl` path. Never raises on bad content."""
    path = Path(path)
    run_dir = path.parent
    now = time.time() if now is None else now
    events, unreadable = _read_events(path)
    start = next((e for e in events if e["kind"] == "run_start"), events[0] if events else None)
    end = next((e for e in reversed(events) if e["kind"] == "run_end"), None)
    flow = str(start.get("flow")) if start and start.get("flow") else "write"
    started = _parse_ts(start.get("ts")) if start else None
    ended = _parse_ts(end.get("ts")) if end else None
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    if not events:
        status = "unknown"
    elif end is not None:
        status = "done" if end.get("exit", "OK") == "OK" else "failed"
    elif mtime is not None and now - mtime > _max_age_minutes() * 60:
        status = "stalled"
    else:
        status = "running"
    verdicts = [e.get("verdict") for e in events if e["kind"] == "audit_verdict"]
    docx = None
    for e in events:
        if e["kind"] == "file_written" and isinstance(e.get("path"), str) and e["path"].lower().endswith(".docx"):
            docx = e["path"]
    tokens, cost = _usage(run_dir)
    last_ts = max((t for t in (_parse_ts(e.get("ts")) for e in events) if t is not None), default=None)
    if started is None:
        elapsed = 0
    elif ended is not None:
        elapsed = int(max(0, ended - started))
    elif status == "running":
        elapsed = int(max(0, now - started))
    else:
        elapsed = int(max(0, (last_ts or started) - started))
    return {
        "run": run_dir.name,
        "flow": flow,
        "workspace": workspace,
        "course": course,
        "started": start.get("ts") if start else None,
        "ended": end.get("ts") if end else None,
        "status": status,
        "steps": _steps(flow, events, end is not None, end is not None and end.get("exit", "OK") == "OK"),
        "units": _units(events),
        "last_verdict": verdicts[-1] if verdicts else None,
        "redrafted": sum(1 for e in events if e["kind"] == "redraft"),
        "docx": docx,
        "tokens": tokens,
        "cost_usd": cost,
        "elapsed_s": elapsed,
        "unreadable": unreadable,
    }


def list_runs(workspaces: List[Dict[str, Any]], limit: int = 50, now: Optional[float] = None) -> Dict[str, List[RunView]]:
    """`{active: [running runs], history: [every other run, newest first, at most `limit`]}` over the workspaces.

    A workspace row without a reachable folder is skipped here (its own page flags it as not found)."""
    views: List[RunView] = []
    for row in workspaces:
        base = row.get("path") if isinstance(row, dict) else None
        if not isinstance(base, str):
            continue
        runs = Path(base) / ".academic-helper" / "runs"
        try:
            files = sorted(runs.glob("*/activity.jsonl"))
        except OSError:
            continue
        for file in files:
            views.append(read_run(file, workspace=base, course=row.get("course"), now=now))
    views.sort(key=lambda v: (v["started"] or "", v["run"]), reverse=True)
    return {
        "active": [v for v in views if v["status"] == "running"],
        "history": [v for v in views if v["status"] != "running"][: max(0, limit)],
    }


def _main(argv: List[str]) -> int:
    if len(argv) >= 2 and argv[0] == "show":
        print(json.dumps(read_run(Path(argv[1])), ensure_ascii=False, indent=2))
        return 0
    if argv and argv[0] == "list" and "--workspaces" in argv:
        rows = json.loads(Path(argv[argv.index("--workspaces") + 1]).read_text(encoding="utf-8"))
        limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 50
        print(json.dumps(list_runs(rows, limit), ensure_ascii=False, indent=2))
        return 0
    print("usage: activity.py show <activity.jsonl> | list --workspaces <workspaces.json> [--limit N]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
