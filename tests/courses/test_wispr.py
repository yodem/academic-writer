import json
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

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
                 "transcriptReady integer, isDeleted integer, recordedMs integer, summary text, speakerMap text, "
                 "notes text, participantNames text, transcript text)")
    rows = [(TIKVA, "t1", "2026-10-13 13:04:49.396 +00:00", 1791901560843, 1, 1, 0, 4871478, "sum tikva", None),
            (HAVAYA, "t2", "2026-10-16 09:01:31.485 +00:00", 1792145991886, 1, 1, 0, 4700560, "sum havaya", None)]
    rows += [(i, "PRIVATE TITLE", c, e, 1, 1, 0, 600000, "PRIVATE SUMMARY", None) for i, c, e in WORK]
    rows += list(extra_meetings)
    conn.executemany("insert into Meetings (id, title, createdAt, endedAt, finalized, transcriptReady, isDeleted, recordedMs, "
                     "summary, speakerMap) values (?,?,?,?,?,?,?,?,?,?)", rows)
    conn.execute("update Meetings set notes = 'PRIVATE NOTES', participantNames = 'PRIVATE PEOPLE', transcript = 'PRIVATE TEXT'")
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
            locked.payload.setdefault("lessons", []).append({"date": kw["lesson_date"], "lesson_key": key, "status": "queued",
                                                             **(kw.get("lesson_owner") or {})})
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


SECOND = ("second-same-day", "x", "2026-10-16 10:25:00.000 +00:00", 1792148100000, 1, 1, 0, 1800000, "sum2", None)


def _with_second(tmp_path):
    reg, wdir = build(tmp_path, extra_meetings=[SECOND])
    d = wdir / "meetings" / SECOND[0]
    d.mkdir()
    (d / "refined.ndjson").write_text(json.dumps({"id": "1", "timestamp": "00:01", "text": "עוד", "speaker": {"id": 1, "name": None}}, ensure_ascii=False) + "\n", encoding="utf-8")
    return reg, wdir


def test_two_same_day_meetings_one_import_one_alternate(tmp_path):
    reg, _ = _with_second(tmp_path)
    calls = []
    report = wispr.scan(reg, add_source=fake_add_source(calls))
    assert [c[1] for c in calls] == ["havaya"]
    actions = {m["id"]: m["action"] for m in report["matched"] if m["slug"] == "havaya"}
    assert sorted(actions.values()) == ["alternate", "import"]
    havaya = json.loads((reg.directory / "havaya.json").read_text())
    assert len(havaya["lessons"]) == 1 and havaya["lessons"][0]["alternates"][0]["meeting_id"] in (HAVAYA, SECOND[0])
    dry = wispr.scan(_with_second(tmp_path / "d")[0], dry_run=True)
    assert sorted(m["action"] for m in dry["matched"] if m["slug"] == "havaya") == ["alternate", "import"]


def test_incomplete_import_is_resumed_not_shelved(tmp_path):
    reg, _ = build(tmp_path)
    state = {"fail": True}

    def flaky(registry, path, slug, **kw):
        # like ingest_recording: the pending lesson is persisted, then the transcript/queue step fails
        with courses._locked_course(registry.directory, slug) as locked:
            key = f"{kw['lesson_date']}-{kw['lesson_time']}"
            if not any(x["lesson_key"] == key for x in locked.payload["lessons"]):
                locked.payload["lessons"].append({"date": kw["lesson_date"], "lesson_key": key, "status": "pending_transcript",
                                                  "audio_sha256": courses._file_sha256(Path(path)), **(kw.get("lesson_owner") or {})})
                courses._atomic_json(locked.path, locked.payload)
        if state["fail"]:
            raise courses.IngestError("transcript failed")
        with courses._locked_course(registry.directory, slug) as locked:
            for x in locked.payload["lessons"]:
                if x["lesson_key"] == key:
                    x["status"] = "queued"
            courses._atomic_json(locked.path, locked.payload)
        return {"status": "ingested", "lesson_key": key}

    first = wispr.scan(reg, add_source=flaky)
    assert [e["id"] for e in first["errors"]] == [HAVAYA]
    pending = json.loads((reg.directory / "havaya.json").read_text())["lessons"][0]
    assert pending["status"] == "pending_transcript" and pending["wispr_meeting_id"] == HAVAYA  # owned before the failure
    seen = json.loads((reg.directory / "term.json").read_text())["state"]["wispr_seen"]
    assert HAVAYA not in seen
    state["fail"] = False
    second = wispr.scan(courses.Registry(reg.directory), add_source=flaky)
    assert [m["action"] for m in second["matched"] if m["slug"] == "havaya"] == ["resume"]
    havaya = json.loads((reg.directory / "havaya.json").read_text())
    assert len(havaya["lessons"]) == 1 and havaya["lessons"][0]["status"] == "queued"
    assert havaya["lessons"][0]["wispr_meeting_id"] == HAVAYA and "alternates" not in havaya["lessons"][0]
    assert HAVAYA in json.loads((reg.directory / "term.json").read_text())["state"]["wispr_seen"]


# ---- privacy: the live database is read in place, read-only, and private columns only for matched meetings

ALLOWED = {"id", "createdAt", "endedAt", "recordedMs", "finalized", "transcriptReady", "isDeleted",
           ""}  # "": a table access with no column, e.g. count(*)


def _no_copies(monkeypatch):
    copies = []
    for mod, name in ((tempfile, "mkdtemp"), (tempfile, "mkstemp"), (shutil, "copyfile"), (shutil, "copy"), (shutil, "copy2"), (shutil, "copytree")):
        def spy(*a, _n=name, **k):
            copies.append((_n, a))
            raise AssertionError(f"{_n} called")
        monkeypatch.setattr(mod, name, spy)
    return copies


def _spy_reads(monkeypatch, wdir, log):
    """Log every column the scan reads from Meetings, with the parameters of the statement that read it."""
    real_connect = sqlite3.connect

    class Spy(sqlite3.Connection):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.params = ()
            self.set_authorizer(self._auth)

        def _auth(self, action, arg1, arg2, dbname, source):
            if action == sqlite3.SQLITE_READ and arg1 == "Meetings":
                log.append(("read", arg2, self.params))
            return sqlite3.SQLITE_OK

        def execute(self, sql, params=()):
            self.params = tuple(params)
            return super().execute(sql, params)

    def connect(*a, **k):
        k["factory"] = Spy
        k["cached_statements"] = 0  # every statement is prepared, so the authorizer sees every read
        return real_connect(*a, **k)
    monkeypatch.setattr(sqlite3, "connect", connect)
    real_match = wispr.match_course

    def match(registry, start, end):
        result = real_match(registry, start, end)
        log.append(("match", start, result[0]))
        return result
    monkeypatch.setattr(wispr, "match_course", match)


@pytest.mark.parametrize("dry_run", [False, True])
def test_private_columns_read_only_for_matched_meetings_after_matching(tmp_path, monkeypatch, dry_run):
    twin = {"slug": "twin", "slots": [{"day": "Tue", "start": "16:00", "end": "18:00", "semester": "A"}]}
    reg, wdir = build(tmp_path, extra_courses=[twin])  # TIKVA becomes ambiguous; the four work meetings match nothing
    ids_by_start = {m["start"]: m["id"] for m in wispr.list_meetings(wdir / "flow.sqlite")}
    log = []
    _spy_reads(monkeypatch, wdir, log)
    _no_copies(monkeypatch)
    report = wispr.scan(reg, dry_run=dry_run, add_source=fake_add_source([]))
    monkeypatch.undo()
    assert {m["id"] for m in report["matched"]} == {HAVAYA} and not report["errors"]
    assert {u["id"] for u in report["unmatched"]} == {TIKVA} | {i for i, _, _ in WORK}
    matched_so_far: set[str] = set()
    private_reads = []
    for event in log:
        if event[0] == "match":
            if event[2]:
                matched_so_far.add(ids_by_start[event[1]])
            continue
        _, column, params = event
        if column in ALLOWED:
            continue
        private_reads.append((column, params))
        assert params and set(params) <= matched_so_far, f"{column} read for {params} before or without a match"
    touched = {i for _, p in private_reads for i in p}
    assert not touched & ({TIKVA} | {i for i, _, _ in WORK})
    assert touched == (set() if dry_run else {HAVAYA})  # the spy works: the matched import did read its summary
    assert "PRIVATE" not in json.dumps(report)


def test_readonly_open_failure_imports_nothing_and_copies_nothing(tmp_path, monkeypatch, capsys):
    reg, wdir = build(tmp_path)
    term_before = (reg.directory / "term.json").read_bytes()
    real_connect = sqlite3.connect
    attempts, sleeps, calls = [], [], []

    def connect(target, *a, **k):
        if str(wdir) in str(target) or str(wdir).replace(" ", "%20") in str(target):
            attempts.append(str(target))
            raise sqlite3.OperationalError("unable to open database file")
        return real_connect(target, *a, **k)
    monkeypatch.setattr(sqlite3, "connect", connect)
    monkeypatch.setattr(time, "sleep", sleeps.append)
    copies = _no_copies(monkeypatch)
    for dry_run in (False, True):
        with pytest.raises(courses.IngestError, match="read-only"):
            wispr.scan(reg, dry_run=dry_run, add_source=fake_add_source(calls))
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(reg.directory.parent))
    assert courses.main(["--term", reg.directory.name, "wispr-scan", "--json"]) != 0
    assert "read-only" in capsys.readouterr().err
    assert calls == [] and copies == [] and len(attempts) >= 2 and sleeps  # retried, never copied
    assert all("mode=ro" in a for a in attempts)
    assert (reg.directory / "term.json").read_bytes() == term_before
    assert not (reg.directory / "digest").exists() and not (reg.directory / "wispr").exists()


def test_database_lost_after_matching_fails_closed_before_any_write(tmp_path, monkeypatch):
    reg, wdir = build(tmp_path)
    term_before = (reg.directory / "term.json").read_bytes()
    real_connect = sqlite3.connect
    opened = []

    def connect(target, *a, **k):
        if str(target).endswith("mode=ro"):
            opened.append(target)
            if len(opened) > 1:  # the metadata query worked; every later open fails
                raise sqlite3.OperationalError("unable to open database file")
        return real_connect(target, *a, **k)
    monkeypatch.setattr(sqlite3, "connect", connect)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    calls = []
    with pytest.raises(courses.IngestError, match="nothing was imported"):
        wispr.scan(reg, add_source=fake_add_source(calls))
    assert calls == [] and len(opened) > 2
    assert (reg.directory / "term.json").read_bytes() == term_before
    assert not (reg.directory / "digest").exists() and not (reg.directory / "wispr").exists() and not (reg.directory / "lessons").exists()
    assert "alternates" not in json.loads((reg.directory / "tikva.json").read_text())["lessons"][0]


def test_transient_open_failure_is_retried(tmp_path, monkeypatch):
    reg, wdir = build(tmp_path)
    real_connect = sqlite3.connect
    state = {"fail": 1}

    def connect(target, *a, **k):
        if state["fail"] and str(target).endswith("mode=ro"):
            state["fail"] -= 1
            raise sqlite3.OperationalError("database is locked")
        return real_connect(target, *a, **k)
    monkeypatch.setattr(sqlite3, "connect", connect)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    report = wispr.scan(reg, dry_run=True)
    assert len(report["matched"]) == 2 and len(report["unmatched"]) == 4


# ---- an import that fails before creating a lesson leaves nothing for a later recording to attach to

def test_failed_first_same_day_import_does_not_shelve_the_second(tmp_path):
    reg, _ = _with_second(tmp_path)
    calls = []
    ok = fake_add_source(calls)

    def add(registry, path, slug, **kw):
        if HAVAYA[:8] in Path(path).name:
            raise courses.IngestError("Drive copy failed")
        return ok(registry, path, slug, **kw)
    report = wispr.scan(reg, add_source=add)
    assert [e["id"] for e in report["errors"]] == [HAVAYA]
    second = next(m for m in report["matched"] if m["id"] == SECOND[0])
    assert second["action"] == "import" and second["lesson_key"] == "2026-10-16-1325"
    havaya = json.loads((reg.directory / "havaya.json").read_text())
    assert [x["lesson_key"] for x in havaya["lessons"]] == ["2026-10-16-1325"] and "alternates" not in havaya["lessons"][0]
    assert not (reg.directory / "lessons" / "havaya" / "2026-10-16-1201").exists()
    seen = json.loads((reg.directory / "term.json").read_text())["state"]["wispr_seen"]
    assert HAVAYA not in seen and SECOND[0] in seen


def test_record_alternate_requires_an_existing_lesson(tmp_path):
    reg, wdir = build(tmp_path)
    with pytest.raises(courses.IngestError, match="no lesson"):
        wispr._record_alternate(reg, "havaya", {"lesson_key": "2026-10-16-1201"}, HAVAYA, wdir / "meetings" / HAVAYA, "sum havaya")
    assert not (reg.directory / "lessons" / "havaya").exists()
    assert json.loads((reg.directory / "havaya.json").read_text())["lessons"] == []


# ---- resume only a lesson this very meeting owns

def _pending_havaya(reg, wdir, owner=None):
    day, hm = "2026-10-16", "1201"
    staged = wispr._staged_path(reg, "havaya", HAVAYA, day, hm)
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(wispr._compose(wdir / "meetings" / HAVAYA, "sum havaya"), encoding="utf-8")
    lesson = {"date": day, "lesson_key": f"{day}-{hm}", "status": "pending_transcript", "audio_sha256": courses._file_sha256(staged)}
    if owner:
        lesson["wispr_meeting_id"] = owner
    path = reg.directory / "havaya.json"
    course = json.loads(path.read_text())
    course["lessons"] = [lesson]
    path.write_text(json.dumps(course), encoding="utf-8")


@pytest.mark.parametrize("owner", [None, "someone-else"])
def test_pending_lesson_not_owned_by_the_meeting_is_never_resumed(tmp_path, owner):
    reg, wdir = build(tmp_path)
    _pending_havaya(reg, wdir, owner)  # same staged-file hash, but no (or another) owner
    calls = []
    report = wispr.scan(reg, add_source=fake_add_source(calls))
    assert all(c[1] != "havaya" for c in calls)
    assert not [m for m in report["matched"] if m["id"] == HAVAYA]
    assert [e["id"] for e in report["errors"]] == [HAVAYA] and "owner" in report["errors"][0]["error"]
    lesson = json.loads((reg.directory / "havaya.json").read_text())["lessons"][0]
    assert lesson.get("wispr_meeting_id") == owner and "alternates" not in lesson
    assert HAVAYA not in json.loads((reg.directory / "term.json").read_text())["state"]["wispr_seen"]


# ---- matching

def test_duration_and_overlap_use_utc_instants_across_dst_end(tmp_path):
    night = {"slug": "night", "slots": [{"day": "Sun", "start": "01:30", "end": "03:00", "semester": "A"}]}
    reg, _ = build(tmp_path, extra_courses=[night])
    utc = timezone.utc
    start = datetime(2026, 10, 24, 22, 50, tzinfo=utc)  # 2026-10-25 01:50+03:00
    end = datetime(2026, 10, 24, 23, 40, tzinfo=utc)    # 2026-10-25 01:40+02:00, 50 minutes later
    assert wispr.match_course(reg, start, end) == ("night", None)


def test_semester_endpoints_and_yearly_gap(tmp_path):
    reg, _ = build(tmp_path)
    tz = ZoneInfo("Asia/Jerusalem")
    cases = {
        "2026-10-11T14:05": "kane",      # first day of semester A
        "2026-10-04T14:05": None,        # the Sunday before it
        "2027-01-26T16:05": "tikva",     # last Tuesday of A
        "2027-01-29T12:05": "havaya",    # last day of A, yearly course
        "2027-02-02T16:05": None,        # a Tuesday between semesters: neither tikva (A) nor levinas (B)
        "2027-02-12T12:05": None,        # a Friday in the yearly course's gap
        "2027-03-05T12:05": None,        # the Friday before B starts
        "2027-03-09T16:05": "levinas",   # first Tuesday of B
        "2027-03-12T12:05": "havaya",    # the yearly course resumes in B
        "2027-06-25T12:05": "havaya",    # last day of B
        "2027-07-02T12:05": None,        # after B
    }
    for local, slug in cases.items():
        start = datetime.fromisoformat(local).replace(tzinfo=tz)
        assert wispr.match_course(reg, start, start + timedelta(minutes=90))[0] == slug, local
