import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "scripts" / "courses"))
import courses
import wispr

TIKVA = "b5cbcfe2-6c69-43b2-98c3-e608d965d329"
HAVAYA = "d5a4c087-e7bc-4395-9b84-724be297423b"
WORK = [
    ("d9ece5e4-f5ba-4da8-a12a-d61f7f075e92", "2026-10-05 11:29:30.336 +00:00", 1791200220439),
    ("ee138c4e-adf8-4a85-91b4-4372968866e2", "2026-10-14 05:56:54.442 +00:00", 1791959553655),
    ("ce64cfc8-54e0-4d2d-a234-7d978d1f58d0", "2026-10-14 11:52:52.826 +00:00", 1791979765088),
    ("d54567d5-92b5-4a08-8969-a3a872618495", "2026-10-14 16:19:11.112 +00:00", 1791995584042),
]


def build(tmp_path, extra_meetings=(), extra_courses=()):
    wdir = tmp_path / "wispr"
    (wdir / "meetings").mkdir(parents=True)
    conn = sqlite3.connect(wdir / "flow.sqlite")
    conn.execute("create table Meetings (id text, title text, createdAt text, endedAt integer, finalized integer, "
                 "transcriptReady integer, isDeleted integer, recordedMs integer, summary text, speakerMap text)")
    rows = [(TIKVA, "t1", "2026-10-13 13:04:49.396 +00:00", 1791901560843, 1, 1, 0, 4871478, "sum tikva", None),
            (HAVAYA, "t2", "2026-10-16 09:01:31.485 +00:00", 1792145991886, 1, 1, 0, 4700560, "sum havaya", None)]
    rows += [(i, "PRIVATE TITLE", c, e, 1, 1, 0, 600000, "PRIVATE SUMMARY", None) for i, c, e in WORK]
    rows += list(extra_meetings)
    conn.executemany("insert into Meetings values (?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    for mid in (TIKVA, HAVAYA):  # only the matching meetings have a readable transcript; work meetings have none at all
        d = wdir / "meetings" / mid
        d.mkdir()
        (d / "refined.ndjson").write_text(
            json.dumps({"id": "1", "timestamp": "00:05", "text": "שלום", "speaker": {"id": 1, "name": None}}, ensure_ascii=False) + "\n"
            + json.dumps({"id": "2", "timestamp": "00:09", "text": "ברוכים", "speaker": {"id": 2, "name": "המרצה"}}, ensure_ascii=False) + "\n",
            encoding="utf-8")
    reg = tmp_path / "reg"
    reg.mkdir()
    (reg / "term.json").write_text(json.dumps({
        "term": "T", "timezone": "Asia/Jerusalem", "wispr_dir": str(wdir),
        "semesters": {"A": {"start": "2026-10-11", "end": "2027-01-29"}, "B": {"start": "2027-03-07", "end": "2027-06-25"}}}), encoding="utf-8")
    cs = {
        "tikva": {"slug": "tikva", "slots": [{"day": "Tue", "start": "16:00", "end": "18:00", "semester": "A"}],
                  "lessons": [{"date": "2026-10-13", "lesson_key": "2026-10-13-1600", "status": "done", "trove_page": 7}]},
        "havaya": {"slug": "havaya", "slots": [{"day": "Fri", "start": "12:00", "end": "14:00", "semester": "yearly"}], "lessons": []},
        "levinas": {"slug": "levinas", "slots": [{"day": "Tue", "start": "16:00", "end": "18:00", "semester": "B"}]},
        "kane": {"slug": "kane", "slots": [{"day": "Sun", "start": "14:00", "end": "16:00", "semester": "A"}]},
    }
    for c in extra_courses:
        cs[c["slug"]] = c
    for slug, c in cs.items():
        (reg / f"{slug}.json").write_text(json.dumps(c), encoding="utf-8")
    return courses.Registry(reg), wdir


def fake_add_source(calls):
    def add(registry, path, slug, **kw):
        calls.append((Path(path), slug, kw))
        key = f"{kw['lesson_date']}-{kw['lesson_time']}"
        with courses._locked_course(registry.directory, slug) as locked:
            locked.payload.setdefault("lessons", []).append({"date": kw["lesson_date"], "lesson_key": key, "status": "queued"})
            courses._atomic_json(locked.path, locked.payload)
        return {"status": "ingested", "lesson_key": key}
    return add


def test_dry_run_matches_two_and_four_work_meetings_unmatched(tmp_path):
    reg, _ = build(tmp_path)
    report = wispr.scan(reg, dry_run=True)
    assert {m["id"]: m["slug"] for m in report["matched"]} == {TIKVA: "tikva", HAVAYA: "havaya"}
    assert sorted(u["id"] for u in report["unmatched"]) == sorted(i for i, _, _ in WORK)
    assert "PRIVATE" not in json.dumps(report)
    assert not (reg.directory / "digest").exists() and "wispr_seen" not in json.dumps(json.loads((reg.directory / "term.json").read_text()))


def test_import_new_lesson_and_dedupe(tmp_path):
    reg, _ = build(tmp_path)
    calls = []
    report = wispr.scan(reg, add_source=fake_add_source(calls))
    assert [(c[1], c[2]["lesson_date"], c[2]["lesson_time"], c[2]["transcript"]) for c in calls] == [("havaya", "2026-10-16", "1201", True)]
    text = calls[0][0].read_text(encoding="utf-8")
    assert "[00:05] דובר 1: שלום" in text and "[00:09] המרצה: ברוכים" in text and "sum havaya" in text
    assert wispr.UNMATCHED_FILE and len(json.loads((reg.directory / "digest" / wispr.UNMATCHED_FILE).read_text())["meetings"]) == 4
    state = json.loads((reg.directory / "term.json").read_text())["state"]["wispr_seen"]
    assert sorted(state) == sorted([TIKVA, HAVAYA])
    again = wispr.scan(courses.Registry(reg.directory), add_source=fake_add_source(calls))
    assert len(calls) == 1 and again["matched"] == [] and len(again["skipped"]) == 2


def test_existing_lesson_gets_alternate_and_is_not_replaced(tmp_path):
    reg, _ = build(tmp_path)
    calls = []
    wispr.scan(reg, add_source=fake_add_source(calls))
    tikva = json.loads((reg.directory / "tikva.json").read_text())
    lesson = tikva["lessons"][0]
    assert len(tikva["lessons"]) == 1 and lesson["trove_page"] == 7 and lesson["status"] == "done"
    assert lesson["alternates"][0]["meeting_id"] == TIKVA and Path(lesson["alternates"][0]["path"]).is_file()
    assert all(c[1] != "tikva" for c in calls)


def test_ambiguous_is_unmatched(tmp_path):
    twin = {"slug": "twin", "slots": [{"day": "Tue", "start": "16:00", "end": "18:00", "semester": "A"}]}
    reg, _ = build(tmp_path, extra_courses=[twin])
    report = wispr.scan(reg, dry_run=True)
    entry = next(u for u in report["unmatched"] if u["id"] == TIKVA)
    assert entry["reason"].startswith("ambiguous:") and "tikva" in entry["reason"] and "twin" in entry["reason"]


def test_filters_and_tolerance(tmp_path):
    rows = [("deleted", "x", "2026-10-20 13:05:00.000 +00:00", 1792500000000, 1, 1, 1, 100, "s", None),
            ("unfinal", "x", "2026-10-20 13:05:00.000 +00:00", 1792500000000, 0, 1, 0, 100, "s", None),
            ("notready", "x", "2026-10-20 13:05:00.000 +00:00", 1792500000000, 1, 0, 0, 100, "s", None)]
    reg, _ = build(tmp_path, extra_meetings=rows)
    report = wispr.scan(reg, dry_run=True)
    ids = {m["id"] for m in report["matched"]} | {u["id"] for u in report["unmatched"]}
    assert not ids & {"deleted", "unfinal", "notready"}
    # direct tolerance checks
    from datetime import datetime, timedelta, timezone
    utc = timezone.utc
    start = datetime(2026, 10, 20, 12, 45, tzinfo=utc)  # 15:45 local Tue: 15 min early
    assert wispr.match_course(reg, start, start + timedelta(minutes=90))[0] == "tikva"
    start = datetime(2026, 10, 20, 12, 30, tzinfo=utc)  # 30 min early
    assert wispr.match_course(reg, start, start + timedelta(minutes=90))[0] is None
    start = datetime(2026, 10, 20, 14, 40, tzinfo=utc)  # 17:40 local: 20 min overlap of 25 min recording = 80%
    assert wispr.match_course(reg, start, start + timedelta(minutes=25))[0] == "tikva"
    start = datetime(2026, 10, 20, 14, 50, tzinfo=utc)  # 17:50 local: 10 min overlap of 60 = 17%
    assert wispr.match_course(reg, start, start + timedelta(minutes=60))[0] is None


def test_unmatched_transcript_never_opened(tmp_path, monkeypatch):
    reg, wdir = build(tmp_path)
    for mid, _, _ in WORK:
        d = wdir / "meetings" / mid
        d.mkdir()
        (d / "refined.ndjson").write_text("{not json", encoding="utf-8")
        (d / "refined.ndjson").chmod(0)
    opened = []
    real_read_text = Path.read_text

    def spy(self, *a, **k):
        opened.append(str(self))
        return real_read_text(self, *a, **k)
    monkeypatch.setattr(Path, "read_text", spy)
    report = wispr.scan(reg, add_source=fake_add_source([]))
    monkeypatch.undo()
    assert len(report["unmatched"]) == 4 and not report["errors"]
    assert not [p for p in opened if any(mid in p for mid, _, _ in WORK)]
    for mid, _, _ in WORK:
        (wdir / "meetings" / mid / "refined.ndjson").chmod(0o600)


def test_missing_database_is_a_noop(tmp_path):
    reg, wdir = build(tmp_path)
    (wdir / "flow.sqlite").unlink()
    report = wispr.scan(reg)
    assert report["matched"] == [] and "not found" in report["note"]


def test_cli_dry_run_json(tmp_path, capsys, monkeypatch):
    reg, _ = build(tmp_path)
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(reg.directory.parent))
    assert courses.main(["--term", reg.directory.name, "wispr-scan", "--dry-run", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["matched"]) == 2 and len(out["unmatched"]) == 4
