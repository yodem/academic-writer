import http.client
import json
import socket
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "scripts" / "courses"))
import chores
import courses
import dashboard
import tasks

TZ = ZoneInfo("Asia/Jerusalem")
NOW = datetime(2026, 10, 16, 18, 0, tzinfo=TZ)  # a Friday in semester A


def _w(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def make_reg(tmp_path):
    d = tmp_path / "root" / "T1"
    _w(d / "term.json", {"term": "T1", "timezone": "Asia/Jerusalem", "lemida": {"base_url": "https://lms.example"},
                         "semesters": {"A": {"start": "2026-10-11", "end": "2027-01-29"},
                                       "B": {"start": "2027-03-07", "end": "2027-06-25"}}})
    pdf = tmp_path / "beta.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    _w(d / "alpha.json", {"slug": "alpha", "name": "Alpha course", "slots": [{"day": "Sun", "start": "14:00", "end": "16:00", "semester": "A"}],
                          "book_id": "book-alpha", "notebook_id": "nb-alpha", "lessons": []})
    _w(d / "beta.json", {"slug": "beta", "name": "Beta course", "mode": "async", "slots": [], "lessons": [],
                         "sources": [{"sha256": "b" * 64, "sha8": "bbbbbbbb", "title": "Beta reading", "file": str(pdf),
                                      "notebook_source_id": "nb-1", "trove": {"book_id": "bk", "page": 3}, "status": "done"}]})
    _w(d / "gamma.json", {"slug": "gamma", "name": "Gamma course", "slots": [{"day": "Mon", "start": "12:00", "end": "14:00", "semester": "B"}], "lessons": []})
    _w(d / "delta.json", {"slug": "delta", "name": "Delta course", "slots": [{"day": "Tue", "start": "16:00", "end": "18:00", "semester": "yearly"}],
                          "lessons": [{"date": "2026-10-16", "lesson_key": "2026-10-16-1600", "status": "done", "trove_page": 4}]})
    _w(d / "eps.json", {"slug": "eps", "name": "Eps course", "slots": [], "lessons": []})
    _w(d / "links.json", {"alpha": {"lemida_url": "https://lms.example/course/view.php?id=1"}})
    reg = courses.Registry(d)
    a = chores.add_chore(reg, course="alpha", kind="assignment", ref="111", title="Alpha essay", due_at="2026-10-18T08:00:00+03:00")
    b = chores.add_chore(reg, course="beta", kind="assignment", ref="222", title="Beta task", due_at="2026-10-25T23:59:00+02:00")
    e = chores.add_chore(reg, course="eps", kind="assignment", ref="333", title="Eps task", due_at="2026-11-01T23:59:00+02:00")
    chores.add_chore(reg, course="eps", kind="manual", ref="note-1", title="Open the library link by hand")
    _w(d / "refs" / "alpha.json", {"course": "alpha", "refs": [
        {"key": "a-miss", "citation": "Lost article", "status": "not-found", "tasks": [a["id"]]},
        {"key": "a-more", "citation": "Mentioned book", "status": "pending"},
    ]})
    _w(d / "refs" / "eps.json", {"course": "eps", "refs": [
        {"key": "e-pend", "citation": "Pending chapter", "status": "pending", "tasks": [e["id"]]},
    ]})
    tasks.task_link(d, "beta", b["id"], source="bbbbbbbb")
    return d, a, b, e


def by_slug(state):
    return {c["slug"]: c for c in state["courses"]}


# --- state ---------------------------------------------------------------------------------------

def test_next_task_states_and_groups(tmp_path):
    d, a, b, e = make_reg(tmp_path)
    s = dashboard.build_state(d, now=NOW)
    c = by_slug(s)
    assert c["alpha"]["next_task"] == a["id"] and c["alpha"]["state"] == "missing"
    assert c["beta"]["next_task"] == b["id"] and c["beta"]["state"] == "ready"
    assert c["eps"]["state"] == "pending"
    assert [r["course"] for r in s["overview"]["rows"]] == ["alpha", "beta", "eps"]  # nearest due first
    assert "delta" in s["overview"]["quiet"] and s["overview"]["later"] == ["gamma"]
    assert c["delta"]["new_lesson"] is True
    alpha_task = c["alpha"]["tasks"][0]
    assert alpha_task["soon"] and alpha_task["lemida_url"] == "https://lms.example/mod/assign/view.php?id=111"
    assert [i["key"] for i in c["alpha"]["more"]] == ["a-more"]
    assert c["eps"]["notices"][0]["title"] == "Open the library link by hand"
    assert c["alpha"]["links"]["trove_url"] == "https://heytrove.ai/library/book-alpha?page=1"
    assert c["alpha"]["links"]["trove_book_id"] == "book-alpha"


def test_unlinked_task_is_never_ready(tmp_path):
    d, *_ = make_reg(tmp_path)
    reg = courses.Registry(d)
    t = chores.add_chore(reg, course="delta", kind="assignment", ref="444", title="Delta task", due_at="2026-11-02T10:00:00+02:00")
    s = dashboard.build_state(d, now=NOW)
    task = next(x for x in by_slug(s)["delta"]["tasks"] if x["id"] == t["id"])
    assert task["state"] == "unlinked"


def test_missing_text_chore_counts_against_its_task(tmp_path):
    d, *_ = make_reg(tmp_path)
    reg = courses.Registry(d)
    chores.add_chore(reg, course="beta", kind="missing-text", ref="222-second-article", title="Second article")
    c = by_slug(dashboard.build_state(d, now=NOW))["beta"]
    assert c["state"] == "missing" and c["tasks"][0]["missing_count"] == 1
    assert not any(n["title"] == "Second article" for n in c["notices"])  # shown under the task, not twice


def test_lede_names_the_nearest_submission_and_what_it_lacks(tmp_path):
    d, *_ = make_reg(tmp_path)
    lede = dashboard.build_state(d, now=NOW)["lede"]
    text = "".join(seg["t"] for seg in lede)
    assert text.startswith("ביום ראשון ב־08:00 מגישים את Alpha essay בAlpha course")
    assert {"t": "מקור אחד", "mark": "circ"} in lede
    assert "שיעור חדש תומלל בDelta course." in text


def test_queued_fetch_turns_the_task_waiting(tmp_path):
    d, a, b, e = make_reg(tmp_path)
    out = dashboard.queue_fetch(d, "eps", ["e-pend"], e["id"])
    job = json.loads((d / "queue" / "fetch" / out["job"]).read_text())
    assert job["course"] == "eps" and job["refs"] == ["e-pend"] and job["task"] == e["id"]
    assert job["run"] == [f"refs.py fetch --course eps --ref e-pend --task {e['id']}"]
    c = by_slug(dashboard.build_state(d, now=NOW))["eps"]
    assert c["state"] == "waiting" and c["tasks"][0]["items"][0]["queued"] is True
    with pytest.raises(dashboard.RequestError):
        dashboard.queue_fetch(d, "eps", ["no-such-ref"])


def test_ocr_blocked_is_waiting(tmp_path):
    d, a, b, e = make_reg(tmp_path)
    data = json.loads((d / "refs" / "eps.json").read_text())
    data["refs"][0].update(status="downloaded", download_path=str(tmp_path / "beta.pdf"), ocr="BLOCKED: empty page")
    _w(d / "refs" / "eps.json", data)
    assert by_slug(dashboard.build_state(d, now=NOW))["eps"]["state"] == "waiting"


def test_agenda_is_semester_aware(tmp_path):
    d, *_ = make_reg(tmp_path)
    days = dashboard.build_state(d, now=NOW, week="2026-10-14")["agenda"]["days"]
    assert days[0]["date"] == "2026-10-11"  # weeks start on Sunday
    sunday = [(i["type"], i["course"]) for i in days[0]["items"]]
    monday = [(i["type"], i["course"]) for i in days[1]["items"]]
    assert ("class", "alpha") in sunday and ("class", "gamma") not in monday
    assert ("class", "delta") in [(i["type"], i["course"]) for i in days[2]["items"]]
    next_week = dashboard.build_state(d, now=NOW, week="2026-10-18")["agenda"]
    assert ("task", "alpha") in [(i["type"], i["course"]) for i in next_week["days"][0]["items"]]
    spring = dashboard.build_state(d, now=NOW, week="2027-03-08")["agenda"]["days"]
    assert ("class", "gamma") in [(i["type"], i["course"]) for i in spring[1]["items"]]
    assert ("class", "alpha") not in [(i["type"], i["course"]) for i in spring[0]["items"]]
    assert ("class", "delta") in [(i["type"], i["course"]) for i in spring[2]["items"]]  # yearly


def test_dst_switch_keeps_the_local_date(tmp_path):
    d, a, b, e = make_reg(tmp_path)
    beta = by_slug(dashboard.build_state(d, now=NOW))["beta"]["tasks"][0]
    assert beta["due_date"] == "2026-10-25" and beta["due_time"] == "23:59"


def test_empty_install(tmp_path):
    s = dashboard.build_state(None, now=NOW)
    assert s["empty"] and s["courses"] == [] and s["reason"] == "no-registry"
    term_only = tmp_path / "T"
    _w(term_only / "term.json", {"term": "T", "timezone": "Asia/Jerusalem"})
    assert dashboard.build_state(term_only, now=NOW)["reason"] == "no-courses"


def test_state_read_never_writes(tmp_path):
    d, *_ = make_reg(tmp_path)
    before = {p: p.stat().st_mtime_ns for p in d.rglob("*")}
    dashboard.build_state(d, now=NOW)
    assert {p: p.stat().st_mtime_ns for p in d.rglob("*")} == before


# --- server --------------------------------------------------------------------------------------

@pytest.fixture
def server(tmp_path):
    d, a, b, e = make_reg(tmp_path)
    srv = dashboard.DashboardServer(lambda: d, port=0, key="k" * 32, interval=0.1, now=lambda: NOW).start()
    yield srv, d, a, b, e
    srv.close()


def req(srv, method, path, body=None, *, cookie=True, origin="ok", host=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    hdrs = {"Host": host or f"127.0.0.1:{srv.port}"}
    if cookie:
        hdrs["Cookie"] = f"{srv.COOKIE}={srv.key}"
    if origin == "ok":
        hdrs["Origin"] = f"http://127.0.0.1:{srv.port}"
    elif origin:
        hdrs["Origin"] = origin
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    conn.request(method, path, body=data, headers=hdrs)
    resp = conn.getresponse()
    out = resp.status, dict(resp.getheaders()), resp.read()
    conn.close()
    return out


def test_page_and_state_need_the_key(server):
    srv, *_ = server
    status, headers, body = req(srv, "GET", f"/?key={srv.key}", cookie=False, origin=None)
    assert status == 200 and b"<html" in body
    assert "HttpOnly" in headers["Set-Cookie"] and "SameSite=Strict" in headers["Set-Cookie"]
    assert req(srv, "GET", "/", cookie=False, origin=None)[0] == 403
    assert req(srv, "GET", "/?key=wrong", cookie=False, origin=None)[0] == 403
    status, _, body = req(srv, "GET", "/api/state", origin=None)
    assert status == 200 and json.loads(body)["courses"]
    assert req(srv, "GET", "/api/state", cookie=False, origin=None)[0] == 403
    assert req(srv, "GET", "/api/events", cookie=False, origin=None)[0] == 403
    assert req(srv, "GET", "/api/state", origin=None, host="evil.example")[0] == 403  # DNS rebinding
    assert req(srv, "GET", "/img/hero-desk.webp", origin=None)[0] == 200


def test_submit_and_unsubmit_through_tasks(server):
    srv, d, a, *_ = server
    status, _, body = req(srv, "POST", "/api/task/submit", {"course": "alpha", "task": a["id"]})
    assert status == 200 and json.loads(body)["closed_chores"] == [a["id"]]
    stored = json.loads((d / "alpha.json").read_text())["tasks"][0]
    assert stored["status"] == "submitted"
    assert next(c for c in chores.load(courses.Registry(d)) if c["id"] == a["id"])["status"] == "done"
    state = json.loads(req(srv, "GET", "/api/state", origin=None)[2])
    assert by_slug(state)["alpha"]["next_task"] is None
    assert {"course": "alpha", "task": a["id"], "submitted": True} in state["overview"]["rows"]
    assert req(srv, "POST", "/api/task/submit", {"course": "alpha", "task": a["id"]})[0] == 200  # idempotent
    status, _, body = req(srv, "POST", "/api/task/unsubmit", {"course": "alpha", "task": a["id"]})
    assert status == 200 and json.loads(body)["reopened_chores"] == [a["id"]]
    assert next(c for c in chores.load(courses.Registry(d)) if c["id"] == a["id"])["status"] == "open"


def test_post_checks_origin_key_and_type(server):
    srv, d, a, *_ = server
    body = {"course": "alpha", "task": a["id"]}
    assert req(srv, "POST", "/api/task/submit", body, origin="http://evil.example")[0] == 403
    assert req(srv, "POST", "/api/task/submit", body, origin=None)[0] == 403
    assert req(srv, "POST", "/api/task/submit", body, cookie=False)[0] == 403
    assert req(srv, "POST", "/api/task/submit", body, host="localhost:1")[0] == 403
    assert req(srv, "POST", "/api/task/submit", body, headers={"Content-Type": "text/plain"})[0] == 415
    assert req(srv, "POST", "/api/task/submit", {"course": "../etc", "task": a["id"]})[0] == 400
    assert json.loads((d / "alpha.json").read_text()).get("tasks") is None  # nothing was submitted


def test_fetch_post_writes_a_queue_job(server):
    srv, d, a, *_ = server
    status, _, body = req(srv, "POST", "/api/fetch", {"course": "alpha", "refs": ["a-miss"], "task": a["id"]})
    assert status == 200
    jobs = list((d / "queue" / "fetch").glob("*-alpha.json"))
    assert len(jobs) == 1 and json.loads(jobs[0].read_text())["refs"] == ["a-miss"]
    assert req(srv, "POST", "/api/fetch", {"course": "alpha", "refs": ["nope"]})[0] == 400


def test_sse_emits_when_a_registry_file_changes(server):
    srv, d, *_ = server
    sock = socket.create_connection(("127.0.0.1", srv.port), timeout=5)
    sock.sendall((f"GET /api/events HTTP/1.1\r\nHost: 127.0.0.1:{srv.port}\r\n"
                  f"Cookie: {srv.COOKIE}={srv.key}\r\n\r\n").encode())
    buf = b""
    deadline = time.time() + 5
    while b"event: hello" not in buf and time.time() < deadline:
        buf += sock.recv(4096)
    assert b"text/event-stream" in buf and b"event: hello" in buf
    time.sleep(0.3)
    _w(d / "eps.json", {"slug": "eps", "name": "Eps renamed", "slots": [], "lessons": []})
    buf = b""
    deadline = time.time() + 5
    while b"state-changed" not in buf and time.time() < deadline:
        buf += sock.recv(4096)
    sock.close()
    assert b"event: state-changed" in buf


def test_busy_port_falls_back_and_other_hosts_are_refused(tmp_path):
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    taken.listen(1)
    port = taken.getsockname()[1]
    srv = dashboard.DashboardServer(lambda: None, port=port, key="x" * 32).start()
    try:
        assert srv.port != port
        status, _, body = req(srv, "GET", "/api/state", origin=None)
        assert status == 200 and json.loads(body)["empty"] is True
    finally:
        srv.close()
        taken.close()
    with pytest.raises(ValueError):
        dashboard.DashboardServer(lambda: None, host="0.0.0.0")
    assert courses.main(["dashboard", "--host", "0.0.0.0", "--no-open"]) == 2


def test_a_chore_closed_elsewhere_offers_no_undo(tmp_path):
    d, a, *_ = make_reg(tmp_path)
    chores.mark_done(courses.Registry(d), a["id"])  # the watcher saw it handed in; the student never pressed submit
    s = dashboard.build_state(d, now=NOW)
    task = by_slug(s)["alpha"]["tasks"][0]
    assert task["status"] == "submitted" and task["recently_submitted"] is False
    assert not any(r["submitted"] for r in s["overview"]["rows"])
    tasks.task_submit(d, "beta", by_slug(s)["beta"]["next_task"])
    later = dashboard.build_state(d, now=datetime.now(TZ))
    assert by_slug(later)["beta"]["tasks"][0]["recently_submitted"] is True


def test_reading_tasks_are_marked_as_readings(tmp_path):
    d, *_ = make_reg(tmp_path)
    data = json.loads((d / "delta.json").read_text())
    data["tasks"] = [{"id": "s-read1", "title": "Chapter two", "due_at": "2026-10-20T00:00:00+03:00", "chore_ids": [],
                      "status": "open", "submitted_at": None, "kind": "reading"}]
    _w(d / "delta.json", data)
    s = dashboard.build_state(d, now=NOW)
    t = by_slug(s)["delta"]["tasks"][0]
    assert t["reading"] is True and t["kind_word"] == "קריאה" and t["due_time"] == "00:00"
    assert s["overview"]["counts"] == {"submit": 3, "read": 1}
    assert "עד יום שלישי צריך לקרוא לDelta course: Chapter two." in "".join(seg["t"] for seg in s["lede"])


def test_only_https_links_reach_the_page(tmp_path):
    d, *_ = make_reg(tmp_path)
    _w(d / "links.json", {"alpha": {"lemida_url": "javascript:alert(1)", "drive_url": "https://drive.example/x"}})
    links = by_slug(dashboard.build_state(d, now=NOW))["alpha"]["links"]
    assert links["lemida"] is None and links["drive"] == "https://drive.example/x"


def test_two_terms_without_a_choice_say_so(tmp_path, monkeypatch):
    root = tmp_path / "courses"
    (root / "T1").mkdir(parents=True)
    (root / "T2").mkdir()
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(root))
    monkeypatch.delenv("ACADEMIC_TERM", raising=False)
    assert dashboard.resolve_directory() is None and dashboard.missing_reason() == "ambiguous-term"
    assert dashboard.missing_reason("T1") == "no-registry"
    assert dashboard.build_state(None, now=NOW, reason="ambiguous-term")["reason"] == "ambiguous-term"


# --- review fixes: per-course task ids, time-driven updates -----------------------------------------

def _spec_task(d, slug, title):
    data = json.loads((d / f"{slug}.json").read_text())
    data["tasks"] = [{"id": "s-t2", "title": title, "due_at": "2026-10-28T10:00:00+02:00", "chore_ids": [],
                      "status": "open", "submitted_at": None, "kind": "spec", "spec_key": "t2"}]
    _w(d / f"{slug}.json", data)


def test_same_task_id_in_two_courses_submits_only_the_named_course(server):
    srv, d, *_ = server
    _spec_task(d, "gamma", "Gamma t2")
    _spec_task(d, "delta", "Delta t2")
    state = json.loads(req(srv, "GET", "/api/state", origin=None)[2])
    assert {(r["course"], r["task"]) for r in state["overview"]["rows"]} >= {("delta", "s-t2")}
    status, _, _ = req(srv, "POST", "/api/task/submit", {"course": "gamma", "task": "s-t2"})
    assert status == 200
    assert json.loads((d / "gamma.json").read_text())["tasks"][0]["status"] == "submitted"
    assert json.loads((d / "delta.json").read_text())["tasks"][0]["status"] == "open"


def test_page_keys_tasks_by_course_and_id():
    root = Path(dashboard.ASSETS)  # the page is a shell plus one script per view
    page = "".join(f.read_text(encoding="utf-8") for f in [root / "index.html", *sorted((root / "views").glob("*.js"))])
    assert "TM[t.id]" not in page and "TM[tkey(t)]" in page
    assert "S.moved[t.id]" not in page and "S.moved[tkey(t)]" in page
    assert "{course:t.course, task:t.id}" in page


def test_next_boundary_is_midnight_or_the_nearest_due(tmp_path):
    d, a, *_ = make_reg(tmp_path)
    state = dashboard.build_state(d, now=NOW)
    # alpha is due 18.10 08:00, so its 72-hour "soon" mark started already; the next change is midnight
    assert dashboard.next_boundary(state, NOW) == datetime(2026, 10, 17, 0, 0, tzinfo=TZ)
    late = datetime(2026, 10, 18, 7, 30, tzinfo=TZ)
    assert dashboard.next_boundary(dashboard.build_state(d, now=late), late) == datetime(2026, 10, 18, 8, 0, tzinfo=TZ)
    # beta is due 25.10 23:59 +02:00 (after the DST switch); 72 hours earlier is 23.10 00:59 local (+03:00)
    early = datetime(2026, 10, 23, 0, 30, tzinfo=TZ)
    assert dashboard.next_boundary(dashboard.build_state(d, now=early), early) == datetime(2026, 10, 23, 0, 59, tzinfo=TZ)


def test_sse_emits_when_the_clock_crosses_a_boundary(tmp_path):
    d, *_ = make_reg(tmp_path)
    clock = [datetime(2026, 10, 16, 23, 59, 30, tzinfo=TZ)]
    srv = dashboard.DashboardServer(lambda: d, port=0, key="c" * 32, interval=0.1, now=lambda: clock[0]).start()
    try:
        sock = socket.create_connection(("127.0.0.1", srv.port), timeout=5)
        sock.sendall((f"GET /api/events HTTP/1.1\r\nHost: 127.0.0.1:{srv.port}\r\n"
                      f"Cookie: {srv.COOKIE}={srv.key}\r\n\r\n").encode())
        buf = b""
        deadline = time.time() + 5
        while b"event: hello" not in buf and time.time() < deadline:
            buf += sock.recv(4096)
        time.sleep(0.4)
        sock.settimeout(0.5)
        quiet = b""
        try:
            quiet = sock.recv(4096)
        except socket.timeout:
            pass
        assert b"state-changed" not in quiet  # no file changed and no boundary passed
        clock[0] = datetime(2026, 10, 17, 0, 0, 5, tzinfo=TZ)  # local midnight passed
        sock.settimeout(5)
        buf = b""
        deadline = time.time() + 5
        while b"state-changed" not in buf and time.time() < deadline:
            buf += sock.recv(4096)
        sock.close()
        assert b"event: state-changed" in buf
    finally:
        srv.close()


def test_soon_mark_flips_exactly_at_the_scheduled_boundary_across_dst(tmp_path):
    """72 hours before a deadline after the 25.10 switch: build_state and next_boundary must agree to the second."""
    d, *_ = make_reg(tmp_path)
    data = json.loads((d / "gamma.json").read_text())
    data["tasks"] = [{"id": "s-dst", "title": "After the switch", "due_at": "2026-10-26T12:00:00+02:00", "chore_ids": [],
                      "status": "open", "submitted_at": None, "kind": "spec"}]
    _w(d / "gamma.json", data)
    gamma = lambda s: by_slug(s)["gamma"]["tasks"][0]  # noqa: E731
    start = datetime(2026, 10, 23, 9, 0, tzinfo=TZ)
    boundary = dashboard.next_boundary(dashboard.build_state(d, now=start), start)
    while boundary is not None and boundary.hour == 0 and boundary.minute == 0:  # skip midnights
        boundary = dashboard.next_boundary(dashboard.build_state(d, now=boundary), boundary)
    assert boundary == datetime(2026, 10, 23, 13, 0, tzinfo=TZ)  # 72 real hours before 26.10 12:00 +02:00
    before = boundary - timedelta(seconds=1)
    assert gamma(dashboard.build_state(d, now=before))["soon"] is False
    assert gamma(dashboard.build_state(d, now=boundary))["soon"] is True


def test_undo_window_closes_exactly_at_the_scheduled_boundary_across_dst(tmp_path):
    d, *_ = make_reg(tmp_path)
    data = json.loads((d / "gamma.json").read_text())
    data["tasks"] = [{"id": "s-sub", "title": "Handed in", "due_at": None, "chore_ids": [], "closed_chores": [],
                      "status": "submitted", "submitted_at": "2026-10-25T00:30:00+03:00", "kind": "spec"}]
    _w(d / "gamma.json", data)
    gamma = lambda s: by_slug(s)["gamma"]["tasks"][0]  # noqa: E731
    start = datetime(2026, 10, 25, 1, 0, tzinfo=TZ)
    boundary = dashboard.next_boundary(dashboard.build_state(d, now=start), start)
    assert boundary == datetime(2026, 10, 25, 11, 30, tzinfo=TZ)  # 12 real hours; the clock fell back at 02:00
    assert gamma(dashboard.build_state(d, now=boundary - timedelta(seconds=1)))["recently_submitted"] is True
    assert gamma(dashboard.build_state(d, now=boundary))["recently_submitted"] is False


# --- extract on request ---------------------------------------------------------------------------

def _downloaded_ref(tmp_path, d):
    pdf = tmp_path / "ref.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    data = json.loads((d / "refs" / "eps.json").read_text())
    data["refs"][0].update(status="downloaded", download_path=str(pdf))
    _w(d / "refs" / "eps.json", data)


def _eps_ref_item(d):
    c = by_slug(dashboard.build_state(d, now=NOW))["eps"]
    return next(i for t in c["tasks"] for i in t["items"] if i["key"] == "e-pend")


def test_downloaded_ref_without_text_is_extractable_and_a_queued_one_says_so(server, tmp_path):
    srv, d, *_ = server
    _downloaded_ref(tmp_path, d)
    item = _eps_ref_item(d)
    assert item["extractable"] and not item["extracted"] and not item["extract_queued"]
    status, _, body = req(srv, "POST", "/api/extract", {"course": "eps", "items": [{"kind": "ref", "key": "e-pend"}]})
    assert status == 200 and json.loads(body)["queued"] == ["ref:e-pend"]
    job = json.loads(next((d / "queue" / "extract").glob("*-eps.json")).read_text())
    assert job["course"] == "eps" and job["items"] == [{"kind": "ref", "key": "e-pend", "method": "auto"}] and job["created_at"]
    item = _eps_ref_item(d)
    assert item["extract_queued"] and not item["extractable"]


def test_extracted_text_ends_extractability(tmp_path):
    d, *_ = make_reg(tmp_path)
    _downloaded_ref(tmp_path, d)
    out = d / "extracted" / "eps" / "ref-e-pend.md"
    out.parent.mkdir(parents=True)
    out.write_text("## עמוד 1\n", encoding="utf-8")
    item = _eps_ref_item(d)
    assert item["extracted"] and not item["extractable"]


def test_source_in_trove_is_extractable_only_while_its_add_source_job_is_pending(tmp_path):
    d, *_ = make_reg(tmp_path)
    src = lambda: next(i for i in by_slug(dashboard.build_state(d, now=NOW))["beta"]["tasks"][0]["items"] if i["key"] == "bbbbbbbb")
    assert src()["downloaded"] and not src()["extractable"]  # already in Trove: it has text
    _w(d / "queue" / "sources" / "beta-bbbbbbbb.json", {"slug": "beta", "sha8": "bbbbbbbb", "file": "x"})
    assert src()["extractable"]  # downloaded, not extracted: the student may choose it
    assert (d / "queue" / "sources" / "beta-bbbbbbbb.json").exists()  # the dashboard never drains it


def test_extract_post_refuses_unknown_items_methods_and_bad_auth(server, tmp_path):
    srv, d, *_ = server
    _downloaded_ref(tmp_path, d)
    ok = {"course": "eps", "items": [{"kind": "ref", "key": "e-pend", "method": "gemini-ocr"}]}
    for bad in ({"course": "eps", "items": [{"kind": "ref", "key": "nope"}]},
                {"course": "eps", "items": [{"kind": "source", "key": "e-pend"}]},     # a ref key under the wrong kind
                {"course": "eps", "items": [{"kind": "file", "key": "x"}]},
                {"course": "eps", "items": []},
                {"course": "eps", "items": "all"},
                {"course": "eps", "items": [{"kind": "ref", "key": "e-pend", "method": "pdftotext"}]},
                {"course": "eps", "method": "rm -rf", "items": [{"kind": "ref", "key": "e-pend"}]},
                {"course": "../etc", "items": [{"kind": "ref", "key": "e-pend"}]},
                {"course": "ghost", "items": [{"kind": "ref", "key": "e-pend"}]}):
        assert req(srv, "POST", "/api/extract", bad)[0] == 400, bad
    assert req(srv, "POST", "/api/extract", ok, cookie=False)[0] == 403
    assert req(srv, "POST", "/api/extract", ok, origin="http://evil.example")[0] == 403
    assert req(srv, "POST", "/api/extract", ok, host="localhost:1")[0] == 403
    assert not (d / "queue" / "extract").exists()  # nothing was written
    assert req(srv, "POST", "/api/extract", ok)[0] == 200
    job = json.loads(next((d / "queue" / "extract").glob("*.json")).read_text())
    assert job["items"][0]["method"] == "gemini-ocr"


def test_extract_job_for_a_source_uses_its_sha8(server):
    srv, d, *_ = server
    assert req(srv, "POST", "/api/extract", {"course": "beta", "method": "claude-vision", "items": [{"kind": "source", "key": "bbbbbbbb"}]})[0] == 200
    job = json.loads(next((d / "queue" / "extract").glob("*-beta.json")).read_text())
    assert job["items"] == [{"kind": "source", "key": "bbbbbbbb", "method": "claude-vision"}]


def test_task_link_skips_a_chore_with_no_known_module_type(tmp_path):
    d, a, b, e = make_reg(tmp_path)
    reg = courses.Registry(d)
    x = chores.add_chore(reg, course="alpha", kind="exam", ref="999", title="Alpha exam")
    tasks.sync_tasks(d, "alpha")  # derives and stores the tasks
    alpha = json.loads((d / "alpha.json").read_text(encoding="utf-8"))
    task = next(t for t in alpha["tasks"] if a["id"] in t["chore_ids"])
    task["chore_ids"] = [x["id"], a["id"]]  # the exam ref has no type; the assignment after it does
    (d / "alpha.json").write_text(json.dumps(alpha, ensure_ascii=False), encoding="utf-8")
    alpha_task = next(t for t in by_slug(dashboard.build_state(d, now=NOW))["alpha"]["tasks"] if t["id"] == task["id"])
    assert alpha_task["lemida_url"] == "https://lms.example/mod/assign/view.php?id=111"
