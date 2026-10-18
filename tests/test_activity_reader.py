"""The agent-activity reader: run views from fixtures, torn lines, stalled runs, cost sums."""
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "activity"

_spec = importlib.util.spec_from_file_location("activity_reader", ROOT / "src" / "scripts" / "activity.py")
activity = importlib.util.module_from_spec(_spec)
sys.modules["activity_reader"] = activity
_spec.loader.exec_module(activity)

START = 1792317600.0  # 2026-10-18T10:00:00Z


def _run(tmp_path, fixture, name="R", mtime=None):
    run_dir = tmp_path / "ws" / ".academic-helper" / "runs" / name
    run_dir.mkdir(parents=True)
    target = run_dir / "activity.jsonl"
    shutil.copy(FIXTURES / fixture, target)
    if mtime is not None:
        os.utime(target, (mtime, mtime))
    return target


def _states(view):
    return {s["id"]: s["state"] for s in view["steps"]}


def test_in_progress_view(tmp_path):
    now = START + 200
    path = _run(tmp_path, "in-progress.jsonl", mtime=now)
    view = activity.read_run(path, workspace="ws", course="Mishnah", now=now)
    assert view["status"] == "running"
    assert view["flow"] == "write" and view["run"] == "R"
    assert view["course"] == "Mishnah" and view["workspace"] == "ws"
    assert view["started"] == "2026-10-18T10:00:00.000Z" and view["ended"] is None
    assert _states(view) == {"outline": "done", "draft": "done", "audit": "current", "redraft": "todo",
                             "synthesize": "todo", "word": "todo"}
    assert {u["id"]: u["state"] for u in view["units"]} == {"intro": "drafted", "U1": "rejected"}
    assert [u for u in view["units"] if u["id"] == "U1"][0]["reason"] == "unknown-source"
    assert view["last_verdict"] == "FAIL" and view["redrafted"] == 0
    assert view["docx"] is None and view["elapsed_s"] == 200
    assert view["tokens"] is None and view["cost_usd"] is None  # no usage.jsonl


def test_done_view_has_docx_and_cost(tmp_path):
    path = _run(tmp_path, "done.jsonl", mtime=START + 600)
    rows = [
        {"run_id": "R", "step": "write.draft", "input_tokens": 1000, "output_tokens": 500, "cost_usd": 0.12},
        {"run_id": "R", "step": "write.synthesize", "input_tokens": 200, "output_tokens": 100, "cost_usd": 0.03},
    ]
    (path.parent / "usage.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    view = activity.read_run(path, now=START + 700)
    assert view["status"] == "done"
    assert view["docx"] == "/tmp/article.docx"
    assert view["tokens"] == 1800 and view["cost_usd"] == 0.15
    assert view["ended"] == "2026-10-18T10:08:32.000Z" and view["elapsed_s"] == 512
    assert view["redrafted"] == 1 and view["last_verdict"] == "PASS"
    states = _states(view)
    assert states["draft"] == "done" and states["synthesize"] == "done" and states["word"] == "done"
    assert {u["id"]: u["state"] for u in view["units"]}["U1"] == "redrafted"


def test_null_cost_makes_the_sum_null(tmp_path):
    path = _run(tmp_path, "done.jsonl")
    rows = [
        {"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.01},
        {"input_tokens": 10, "output_tokens": 5, "cost_usd": None},
    ]
    (path.parent / "usage.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    view = activity.read_run(path, now=START + 700)
    assert view["tokens"] == 30 and view["cost_usd"] is None


def test_reader_skips_torn_last_line(tmp_path):
    now = START + 300
    path = _run(tmp_path, "torn.jsonl", mtime=now)
    view = activity.read_run(path, now=now)
    assert view["status"] == "running"
    assert view["unreadable"] == 1
    assert view["last_verdict"] == "FAIL"
    assert _states(view)["draft"] == "done"
    # A wholly unreadable file still shows, as unknown, and nothing raises.
    bad = tmp_path / "ws2" / ".academic-helper" / "runs" / "X" / "activity.jsonl"
    bad.parent.mkdir(parents=True)
    bad.write_text('{"v":1,"ts":"2026\n', encoding="utf-8")
    unknown = activity.read_run(bad, now=now)
    assert unknown["status"] == "unknown" and unknown["unreadable"] == 1 and unknown["run"] == "X"


def test_stalled_after_threshold(tmp_path):
    limit = activity._max_age_minutes() * 60
    assert limit == 360 * 60
    path = _run(tmp_path, "in-progress.jsonl", mtime=START)
    assert activity.read_run(path, now=START + limit - 60)["status"] == "running"
    stalled = activity.read_run(path, now=START + limit + 60)
    assert stalled["status"] == "stalled"
    assert stalled["elapsed_s"] == 191  # last event time (10:03:11), not "now"


def test_failed_run(tmp_path):
    path = _run(tmp_path, "in-progress.jsonl", mtime=START + 100)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"v": 1, "ts": "2026-10-18T10:04:00.000Z", "run": "R", "flow": "write",
                                 "kind": "run_end", "exit": "ERROR", "reason": "ERROR docx: boom"}) + "\n")
    assert activity.read_run(path, now=START + 200)["status"] == "failed"


def test_list_runs_splits_active_and_history_and_keeps_missing_workspaces(tmp_path):
    now = START + 100
    _run(tmp_path, "in-progress.jsonl", name="live", mtime=now)
    other = tmp_path / "ws" / ".academic-helper" / "runs" / "old"
    other.mkdir(parents=True)
    shutil.copy(FIXTURES / "done.jsonl", other / "activity.jsonl")
    rows = [{"path": str(tmp_path / "ws"), "type": "course", "course": "Mishnah", "exists": True},
            {"path": str(tmp_path / "gone"), "type": "project", "course": None, "exists": False}]
    result = activity.list_runs(rows, limit=1, now=now)
    assert [v["run"] for v in result["active"]] == ["live"]
    assert [v["run"] for v in result["history"]] == ["old"]
    assert result["history"][0]["course"] == "Mishnah"
    assert activity.list_runs(rows, limit=0, now=now)["history"] == []


def test_cli_show(tmp_path):
    path = _run(tmp_path, "done.jsonl")
    out = subprocess.check_output([sys.executable, str(ROOT / "src/scripts/activity.py"), "show", str(path)])
    assert json.loads(out)["status"] == "done"


def _write(tmp_path, rows, name="W", mtime=None):
    run_dir = tmp_path / "ws" / ".academic-helper" / "runs" / name
    run_dir.mkdir(parents=True)
    target = run_dir / "activity.jsonl"
    target.write_text("".join(json.dumps({"v": 1, "run": name, "flow": "write", **r}) + "\n" for r in rows), encoding="utf-8")
    if mtime is not None:
        os.utime(target, (mtime, mtime))
    return target


def test_audit_verdicts_with_a_unit_mark_it_passed_or_rejected(tmp_path):
    path = _write(tmp_path, [
        {"ts": "2026-10-18T10:00:00.000Z", "kind": "run_start"},
        {"ts": "2026-10-18T10:00:01.000Z", "kind": "unit_drafted", "unit": "A"},
        {"ts": "2026-10-18T10:00:02.000Z", "kind": "unit_drafted", "unit": "B"},
        {"ts": "2026-10-18T10:00:03.000Z", "kind": "unit_drafted", "unit": "C"},
        {"ts": "2026-10-18T10:01:00.000Z", "kind": "audit_verdict", "step": "audit", "unit": "A", "paragraph": 0, "verdict": "PASS"},
        {"ts": "2026-10-18T10:01:01.000Z", "kind": "audit_verdict", "step": "audit", "unit": "A", "paragraph": 1, "verdict": "PASS"},
        {"ts": "2026-10-18T10:01:02.000Z", "kind": "audit_verdict", "step": "audit", "unit": "B", "paragraph": 0, "verdict": "FAIL", "reason": "FAIL, 2 issues"},
        {"ts": "2026-10-18T10:01:03.000Z", "kind": "audit_verdict", "step": "audit", "unit": "B", "paragraph": 1, "verdict": "PASS"},
        {"ts": "2026-10-18T10:01:04.000Z", "kind": "audit_verdict", "step": "audit", "unit": "C", "verdict": "unknown"},
        {"ts": "2026-10-18T10:01:05.000Z", "kind": "audit_verdict", "step": "audit", "paragraph": 0, "verdict": "FAIL"},
    ], mtime=START + 100)
    states = {u["id"]: u["state"] for u in activity.read_run(path, now=START + 100)["units"]}
    # A later PASS never hides a rejected paragraph; an unreadable verdict is unknown; a verdict with no unit marks nothing.
    assert states == {"A": "passed", "B": "rejected", "C": "unknown"}


def test_a_redraft_resets_the_audit_result(tmp_path):
    path = _write(tmp_path, [
        {"ts": "2026-10-18T10:00:00.000Z", "kind": "run_start"},
        {"ts": "2026-10-18T10:00:01.000Z", "kind": "unit_drafted", "unit": "B"},
        {"ts": "2026-10-18T10:01:00.000Z", "kind": "audit_verdict", "unit": "B", "verdict": "FAIL"},
        {"ts": "2026-10-18T10:02:00.000Z", "kind": "redraft", "unit": "B"},
        {"ts": "2026-10-18T10:02:01.000Z", "kind": "unit_drafted", "unit": "B"},
        {"ts": "2026-10-18T10:03:00.000Z", "kind": "audit_verdict", "unit": "B", "verdict": "PASS"},
    ], mtime=START + 100)
    assert activity.read_run(path, now=START + 100)["units"][0]["state"] == "passed"


def test_finished_write_run_shows_skipped_not_todo(tmp_path):
    path = _write(tmp_path, [
        {"ts": "2026-10-18T10:00:00.000Z", "kind": "run_start"},
        {"ts": "2026-10-18T10:00:01.000Z", "kind": "step_start", "step": "draft"},
        {"ts": "2026-10-18T10:00:02.000Z", "kind": "step_end", "step": "draft"},
        {"ts": "2026-10-18T10:00:03.000Z", "kind": "step_start", "step": "audit"},
        {"ts": "2026-10-18T10:00:04.000Z", "kind": "audit_verdict", "step": "audit", "unit": "A", "verdict": "PASS"},
        {"ts": "2026-10-18T10:00:05.000Z", "kind": "step_end", "step": "audit"},
        {"ts": "2026-10-18T10:00:06.000Z", "kind": "step_start", "step": "synthesize"},
        {"ts": "2026-10-18T10:00:07.000Z", "kind": "step_end", "step": "synthesize"},
        {"ts": "2026-10-18T10:00:08.000Z", "kind": "step_start", "step": "word"},
        {"ts": "2026-10-18T10:00:09.000Z", "kind": "step_end", "step": "word"},
        {"ts": "2026-10-18T10:00:10.000Z", "kind": "run_end", "exit": "OK"},
    ])
    states = _states(activity.read_run(path, now=START + 100))
    assert states == {"outline": "done", "draft": "done", "audit": "done", "redraft": "skipped",
                      "synthesize": "done", "word": "done"}
    assert "todo" not in states.values()


def test_failed_run_keeps_unreached_steps_todo(tmp_path):
    path = _write(tmp_path, [
        {"ts": "2026-10-18T10:00:00.000Z", "kind": "run_start"},
        {"ts": "2026-10-18T10:00:01.000Z", "kind": "step_start", "step": "draft"},
        {"ts": "2026-10-18T10:00:02.000Z", "kind": "run_end", "exit": "ERROR"},
    ])
    states = _states(activity.read_run(path, now=START + 100))
    assert states["synthesize"] == "todo" and states["redraft"] == "todo"
