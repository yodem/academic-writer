import http.client
import json
import socket
import sys
import time
from datetime import datetime
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
    assert alpha_task["soon"] and alpha_task["lemida_url"] == "https://lms.example/mod/view.php?id=111"
    assert [i["key"] for i in c["alpha"]["more"]] == ["a-more"]
    assert c["eps"]["notices"][0]["title"] == "Open the library link by hand"
    assert c["alpha"]["links"]["trove_url"] is None and c["alpha"]["links"]["trove_book_id"] == "book-alpha"


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
