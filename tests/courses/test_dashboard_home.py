"""Dashboard server, home-aware: roles and nav, setup, writing runs, colours, routes, CSP, SSE."""
import http.client
import json
import os
import shutil
import socket
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src" / "scripts" / "courses"))
sys.path.insert(0, str(HERE))
import chores
import courses
import dashboard
from test_dashboard import _w, by_slug, make_reg

TZ = ZoneInfo("Asia/Jerusalem")
# 2026-10-18T10:10:00Z, ten minutes into tests/fixtures/activity/in-progress.jsonl
NOW = datetime(2026, 10, 18, 13, 10, tzinfo=TZ)  # a Sunday
START = 1792317600.0
FIXTURES = ROOT / "tests" / "fixtures" / "activity"

OK_CHECKS = [{"id": "home", "label_he": "תיקיית בית", "ok": True, "optional": False, "found": "x", "required": None,
              "reason_he": None, "fix": None},
             {"id": "gemini-key", "label_he": "מפתח Gemini", "ok": False, "optional": True, "found": None,
              "required": None, "reason_he": "לא הוגדר מפתח", "fix": "/academic-writer:setup"}]
BAD_CHECKS = [dict(OK_CHECKS[0], ok=False, reason_he="לא נבחרה תיקיית בית", fix="/academic-writer:setup"), OK_CHECKS[1]]


def make_home(tmp_path, role="student", name="דנה", extra=""):
    home = tmp_path / "home"
    meta = home / ".academic-helper"
    meta.mkdir(parents=True)
    (meta / "home.md").write_text(f"---\nname: {name}\nrole: {role}\ninstitution: בר-אילן\ndegree: MA\n{extra}---\n",
                                  encoding="utf-8")
    return home


def make_workspace(tmp_path, home, name="article", fixture="in-progress.jsonl", run="R", mtime=START + 600,
                   wtype="project", course=None):
    ws = tmp_path / name
    target = ws / ".academic-helper" / "runs" / run / "activity.jsonl"
    target.parent.mkdir(parents=True)
    shutil.copy(FIXTURES / fixture, target)
    os.utime(target, (mtime, mtime))
    rows_path = home / ".academic-helper" / "workspaces.json"
    rows = json.loads(rows_path.read_text()) if rows_path.exists() else []
    rows.append({"path": str(ws), "type": wtype, "course": course, "term": None, "created": "2026-10-01T00:00:00Z"})
    rows_path.write_text(json.dumps(rows), encoding="utf-8")
    return ws, target


def start(tmp_path, home, setup=None, directory="reg", now=NOW, **kw):
    if directory == "reg":
        directory = make_reg(tmp_path)[0]
    srv = dashboard.DashboardServer(lambda: directory, port=0, key="k" * 32, interval=0.1, now=lambda: now,
                                    home=lambda: home, setup=lambda: (OK_CHECKS if setup is None else setup), **kw).start()
    return srv


@pytest.fixture
def servers():
    made = []

    def _start(*a, **k):
        srv = start(*a, **k)
        made.append(srv)
        return srv

    yield _start
    for srv in made:
        srv.close()


def req(srv, path, *, method="GET", host=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    conn.request(method, path, headers={"Host": host or f"127.0.0.1:{srv.port}", "Cookie": f"{srv.COOKIE}={srv.key}"})
    resp = conn.getresponse()
    out = resp.status, dict(resp.getheaders()), resp.read()
    conn.close()
    return out


def state(srv):
    status, _, body = req(srv, "/api/state")
    assert status == 200
    return json.loads(body)


# --- roles and nav -------------------------------------------------------------------------------

def test_student_nav(tmp_path, servers):
    home = make_home(tmp_path, "student")
    s = state(servers(tmp_path, home))
    assert s["nav"] == ["overview", "timeline", "courses", "writing", "about"]
    assert s["home"] == {"name": "דנה", "role": "student", "institution": "בר-אילן", "degree": "MA", "missing": False,
                         "configured": True}
    assert s["setup"]["complete"] is True and s["setup"]["checks"] == OK_CHECKS
    assert {c["slug"] for c in s["courses"]} >= {"alpha", "beta"}
    assert s["writing"] == {"active": [], "history": []}


def test_lecturer_nav_has_no_term_views(tmp_path, servers):
    home = make_home(tmp_path, "lecturer")
    s = state(servers(tmp_path, home))  # a registry exists, but a lecturer takes no courses
    assert s["nav"] == ["overview", "writing", "about"]
    assert s["courses"] == [] and s["exams"] == [] and s["term"] is None
    assert s["timeline"] == {"weeks": []}
    assert set(s["overview"]) >= {"primary", "projects", "results", "library"}
    assert s["home"]["role"] == "lecturer"


def test_setup_first_when_incomplete(tmp_path, servers):
    home = make_home(tmp_path, "student")
    s = state(servers(tmp_path, home, setup=BAD_CHECKS))
    assert s["nav"] == ["setup", "overview", "timeline", "courses", "writing", "about"]
    assert s["setup"]["complete"] is False
    s2 = state(servers(tmp_path, home, setup=OK_CHECKS[:1] + [dict(OK_CHECKS[1], ok=False)]))  # only an optional check fails
    assert s2["nav"][0] == "overview" and s2["setup"]["complete"] is True


def test_setup_checks_run_at_most_once_a_minute(tmp_path):
    home = make_home(tmp_path, "student")
    calls = []
    clock = [1000.0]

    def provider():
        calls.append(1)
        return OK_CHECKS

    d = make_reg(tmp_path)[0]
    srv = dashboard.DashboardServer(lambda: d, port=0, key="k" * 32, now=lambda: NOW, home=lambda: home,
                                    setup=provider, monotonic=lambda: clock[0])
    srv.state()
    srv.state()
    assert len(calls) == 1
    clock[0] += 61
    srv.state()
    assert len(calls) == 2


# --- week mode -----------------------------------------------------------------------------------

@pytest.mark.parametrize("when,mode", [
    (datetime(2026, 10, 18, 9, 0, tzinfo=TZ), "week-ahead"),   # Sunday
    (datetime(2026, 10, 17, 18, 0, tzinfo=TZ), "week-ahead"),  # Saturday 18:00
    (datetime(2026, 10, 17, 17, 59, tzinfo=TZ), "today"),
    (datetime(2026, 10, 20, 12, 0, tzinfo=TZ), "today"),       # Tuesday
])
def test_week_mode(tmp_path, when, mode):
    d = make_reg(tmp_path)[0]
    assert dashboard.build_state(d, now=when)["week_mode"] == mode


def test_week_ahead_on_sunday(tmp_path):
    d = make_reg(tmp_path)[0]
    assert dashboard.build_state(d, now=NOW)["week_mode"] == "week-ahead"


def test_today_on_tuesday(tmp_path):
    d = make_reg(tmp_path)[0]
    assert dashboard.build_state(d, now=datetime(2026, 10, 20, 9, 0, tzinfo=TZ))["week_mode"] == "today"


# --- writing -------------------------------------------------------------------------------------

def test_writing_active_from_fixture_run(tmp_path, servers):
    home = make_home(tmp_path, "student")
    ws, _ = make_workspace(tmp_path, home, "live", "in-progress.jsonl", "live")
    make_workspace(tmp_path, home, "old", "done.jsonl", "R1", mtime=START)
    s = state(servers(tmp_path, home))
    assert [r["run"] for r in s["writing"]["active"]] == ["live"]
    assert s["writing"]["active"][0]["status"] == "running"
    assert [r["run"] for r in s["writing"]["history"]] == ["R1"]
    assert {w["path"] for w in s["workspaces"]} == {str(ws), str(tmp_path / "old")}


def test_missing_workspace_is_listed_not_found(tmp_path, servers):
    home = make_home(tmp_path, "student")
    make_workspace(tmp_path, home, "gone", "done.jsonl")
    shutil.rmtree(tmp_path / "gone")
    s = state(servers(tmp_path, home))
    assert [(w["path"], w["exists"]) for w in s["workspaces"]] == [(str(tmp_path / "gone"), False)]


def test_lecturer_overview_from_writing_and_library(tmp_path, servers):
    home = make_home(tmp_path, "researcher")
    ws, _ = make_workspace(tmp_path, home, "paper", "in-progress.jsonl", "live")
    sources = [{"id": "new", "title": "Fresh book", "addedAt": (NOW - timedelta(days=2)).isoformat()},
               {"id": "old", "title": "Old book", "addedAt": (NOW - timedelta(days=30)).isoformat()},
               {"id": "undated", "title": "No date"}]
    (ws / ".academic-helper" / "sources.json").write_text(json.dumps({"sources": sources}), encoding="utf-8")
    ov = state(servers(tmp_path, home))["overview"]
    assert ov["primary"]["run"] == "live"
    assert [p["path"] for p in ov["projects"]] == [str(ws)]
    assert [x["title"] for x in ov["library"]] == ["Fresh book"]
    home2 = make_home(tmp_path / "x", "researcher")
    (tmp_path / "x" / "home" / ".academic-helper" / "workspaces.json").write_text("[]")
    assert state(servers(tmp_path / "x", home2))["overview"]["library"] == []  # hidden when none


# --- course data ---------------------------------------------------------------------------------

def test_colors_stable_and_explicit_wins(tmp_path):
    d = make_reg(tmp_path)[0]
    first = {c["slug"]: c["color"] for c in dashboard.build_state(d, now=NOW)["courses"]}
    again = {c["slug"]: c["color"] for c in dashboard.build_state(d, now=NOW)["courses"]}
    assert first == again
    assert set(first.values()) <= set(dashboard.COURSE_COLORS)
    assert len(set(first.values())) == len(first)  # six courses, eight hues: no two alike
    data = json.loads((d / "beta.json").read_text())
    data["color"] = "olive"
    _w(d / "beta.json", data)
    now = {c["slug"]: c["color"] for c in dashboard.build_state(d, now=NOW)["courses"]}
    assert now["beta"] == "olive"
    assert len(set(now.values())) == len(now)
    data["color"] = "not-a-hue"
    _w(d / "beta.json", data)
    assert by_slug(dashboard.build_state(d, now=NOW))["beta"]["color"] in dashboard.COURSE_COLORS


def test_assign_colors_exact_order():
    cs = dashboard.COURSE_COLORS
    raw = {"zeta": {}, "alpha": {}, "mid": {}}
    assert dashboard.assign_colors(raw, {}) == {"alpha": cs[0], "mid": cs[1], "zeta": cs[2]}
    raw = {"zeta": {}, "alpha": {}, "mid": {"color": cs[0]}, "bad": {"color": "nope"}}
    got = dashboard.assign_colors(raw, {"alpha": {"color": cs[5]}})  # links.json colour is ignored
    assert got == {"alpha": cs[1], "bad": cs[2], "mid": cs[0], "zeta": cs[3]}


def test_exams_timeline_and_wispr(tmp_path):
    d = make_reg(tmp_path)[0]
    reg = courses.Registry(d)
    chores.add_chore(reg, course="delta", kind="exam", ref="555", title="Delta exam", due_at="2026-11-10T09:00:00+02:00",
                     room="B12", material="chapters 1-4")
    _w(d / "links.json", {"alpha": {"wispr_url": "https://wispr.example/alpha"}, "beta": {"wispr_url": "javascript:x"}})
    _w(d / "digest" / "wispr-unmatched.json", {"meetings": [
        {"id": "m1", "start": "2026-10-13T14:00:00+03:00", "reason": "short", "course_guess": "alpha"},
        {"id": "m2", "start": "2026-10-14T14:00:00+03:00", "reason": "short"}]})
    s = dashboard.build_state(d, now=NOW)
    c = by_slug(s)
    assert [(e["course"], e["title"], e["room"], e["material"]) for e in s["exams"]] == \
        [("delta", "Delta exam", "B12", "chapters 1-4")]
    assert c["alpha"]["links"]["wispr"] == "https://wispr.example/alpha" and c["beta"]["links"]["wispr"] is None
    assert c["alpha"]["unmatched_recordings"] == 1 and c["delta"]["unmatched_recordings"] == 0
    weeks = s["timeline"]["weeks"]
    assert weeks[0]["start"] == "2026-10-11" and all(w["start"] <= w2["start"] for w, w2 in zip(weeks, weeks[1:]))
    assert any(i["kind"] == "exam" and i["title"] == "Delta exam" for w in weeks for i in w["items"])
    assert s["overview"]["counts"]["submit"] == 3  # an exam is not a submission


# --- routes, CSP ---------------------------------------------------------------------------------

@pytest.fixture
def assets(tmp_path, monkeypatch):
    root = tmp_path / "assets"
    (root / "views").mkdir(parents=True)
    (root / "views" / "overview.js").write_text("// view", encoding="utf-8")
    (root / "app.css").write_text("/* app */", encoding="utf-8")
    (root / "margin.css").write_text("/* tokens */", encoding="utf-8")
    (root / "about.json").write_text('{"features": []}', encoding="utf-8")
    (root / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(dashboard, "ASSETS", root)
    return root


def test_static_routes(tmp_path, servers, assets):
    srv = servers(tmp_path, make_home(tmp_path))
    for path, ctype in (("/app.css", "text/css"), ("/margin.css", "text/css"), ("/views/overview.js", "text/javascript"),
                        ("/about.json", "application/json")):
        status, headers, _ = req(srv, path)
        assert status == 200 and headers["Content-Type"].startswith(ctype), path
    assert req(srv, "/views/missing.js")[0] == 404
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    conn.request("GET", "/app.css", headers={"Host": f"127.0.0.1:{srv.port}"})  # no key, no cookie
    assert conn.getresponse().status == 403


@pytest.mark.parametrize("path", ["/views/../dashboard.py", "/views/..%2Fdashboard.py", "/views/%2e%2e/dashboard.py",
                                  "/views/a.py", "/views/.js", "/views/A.js", "/views/sub/x.js", "/views/overview.js/"])
def test_view_route_rejects_traversal(tmp_path, servers, assets, path):
    assert req(servers(tmp_path, make_home(tmp_path)), path)[0] == 404


def test_csp_has_no_unsafe_inline(tmp_path, servers, assets):
    srv = servers(tmp_path, make_home(tmp_path))
    for path in ("/", "/api/state", "/app.css"):
        csp = req(srv, path)[1]["Content-Security-Policy"]
        assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
        assert "script-src 'self'" in csp and "style-src 'self'" in csp


# --- live updates and an unreachable home ---------------------------------------------------------

def test_sse_fires_on_activity_append(tmp_path, servers):
    home = make_home(tmp_path, "student")
    _, activity = make_workspace(tmp_path, home, "live", "in-progress.jsonl", "live")
    srv = servers(tmp_path, home)
    sock = socket.create_connection(("127.0.0.1", srv.port), timeout=5)
    sock.sendall((f"GET /api/events HTTP/1.1\r\nHost: 127.0.0.1:{srv.port}\r\n"
                  f"Cookie: {srv.COOKIE}={srv.key}\r\n\r\n").encode())
    buf = b""
    deadline = time.time() + 5
    while b"event: hello" not in buf and time.time() < deadline:
        buf += sock.recv(4096)
    time.sleep(0.4)
    with open(activity, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"v": 1, "ts": "2026-10-18T10:09:00.000Z", "run": "live", "flow": "write",
                             "kind": "unit_drafted", "step": "draft", "unit": "s9"}) + "\n")
    buf = b""
    deadline = time.time() + 5
    while b"state-changed" not in buf and time.time() < deadline:
        buf += sock.recv(4096)
    sock.close()
    assert b"event: state-changed" in buf


def test_home_unreachable_state(tmp_path, servers):
    gone = tmp_path / "moved-away"
    s = state(servers(tmp_path, gone, setup=BAD_CHECKS))
    assert s["home"]["missing"] is True and s["home"]["configured"] is True and s["home"]["name"] is None
    assert s["nav"][0] == "setup"
    assert s["workspaces"] == [] and s["writing"] == {"active": [], "history": []}
    assert s["courses"]  # the term registry still shows
    assert not gone.exists()  # never created


def test_no_home_at_all(tmp_path, servers):
    s = state(servers(tmp_path, None, directory=None))
    assert s["home"]["configured"] is False and s["home"]["missing"] is False and s["home"]["role"] is None
    assert s["nav"] == ["overview", "writing", "about"]


# --- malformed registry rows ---------------------------------------------------------------------

BAD_ROWS = [{"path": 123, "type": "project"}, {"path": None}, {"path": ["a"]}, {"path": {"x": 1}}, "text", 7, None,
            {"path": "/nonexistent/ws", "type": ["unknown"], "course": {"a": 1}}, {"type": "project"}]


def _write_rows(home, rows):
    (home / ".academic-helper" / "workspaces.json").write_text(json.dumps(rows), encoding="utf-8")


def _wait_version_above(srv, v, seconds=5):
    deadline = time.time() + seconds
    while srv.version <= v and time.time() < deadline:
        time.sleep(0.05)
    return srv.version > v


def test_bad_registry_rows_are_skipped_not_fatal(tmp_path, servers):
    home = make_home(tmp_path, "student")
    ws, _ = make_workspace(tmp_path, home)
    rows = json.loads((home / ".academic-helper" / "workspaces.json").read_text())
    _write_rows(home, BAD_ROWS + rows)
    s = state(servers(tmp_path, home))
    assert [w["path"] for w in s["workspaces"] if w["path"] == str(ws)] == [str(ws)]
    assert all(isinstance(w["path"], str) for w in s["workspaces"])
    assert all(isinstance(w["type"], (str, type(None))) and isinstance(w["course"], (str, type(None)))
               for w in s["workspaces"])
    assert len(s["writing"]["active"]) + len(s["writing"]["history"]) == 1


def test_watcher_survives_a_bad_row_and_keeps_emitting(tmp_path, servers):
    home = make_home(tmp_path, "student")
    make_workspace(tmp_path, home)
    good = json.loads((home / ".academic-helper" / "workspaces.json").read_text())
    srv = servers(tmp_path, home)
    state(srv)
    v0 = srv.version
    _write_rows(home, [{"path": 123}] + good)
    assert _wait_version_above(srv, v0), "no state-changed after the bad row was written"
    v1 = srv.version
    _write_rows(home, good + [{"path": str(tmp_path / "other"), "type": "project"}])  # fixed (and changed)
    assert _wait_version_above(srv, v1), "the watcher died after a bad row"
    assert any(t.is_alive() and t.name == "aw-dashboard-watch" for t in srv._threads)


def test_watcher_catches_any_exception_per_iteration(tmp_path, monkeypatch):
    home = make_home(tmp_path, "student")
    d = make_reg(tmp_path)[0]
    srv = dashboard.DashboardServer(lambda: d, port=0, key="k" * 32, interval=0.05, now=lambda: NOW,
                                    home=lambda: home, setup=lambda: OK_CHECKS)
    real = dashboard._signature
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] in (2, 3):
            raise TypeError("boom")
        return real(*a, **k)

    monkeypatch.setattr(dashboard, "_signature", flaky)
    srv.start()
    try:
        time.sleep(0.8)
        assert calls["n"] > 4  # kept looping through the exceptions
        assert any(t.is_alive() and t.name == "aw-dashboard-watch" for t in srv._threads)
    finally:
        srv.close()


# --- setup block ---------------------------------------------------------------------------------

def test_setup_block_only_required_failures_make_it_incomplete():
    base = {"id": "x", "label_he": "x", "found": None, "required": None, "reason_he": None, "fix": None}
    only_optional = [dict(base, ok=False, optional=True), dict(base, ok=None, optional=False),
                     dict(base, ok=None, optional=True), dict(base, ok=True, optional=False)]
    assert dashboard.setup_block(lambda: only_optional)["complete"] is True
    assert dashboard.setup_block(lambda: only_optional + [dict(base, ok=False, optional=False)])["complete"] is False
    assert dashboard.setup_block(lambda: [dict(base, ok=False)])["complete"] is False  # no flag: required
    assert dashboard.setup_block(lambda: [dict(base, ok=None)])["complete"] is True


# --- POST /api/open ------------------------------------------------------------------------------

def post(srv, path, body, *, origin="ok", ctype="application/json"):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    hdrs = {"Host": f"127.0.0.1:{srv.port}", "Cookie": f"{srv.COOKIE}={srv.key}", "Content-Type": ctype}
    if origin == "ok":
        hdrs["Origin"] = f"http://127.0.0.1:{srv.port}"
    elif origin:
        hdrs["Origin"] = origin
    conn.request("POST", path, body=json.dumps(body).encode(), headers=hdrs)
    resp = conn.getresponse()
    out = resp.status, json.loads(resp.read() or b"{}")
    conn.close()
    return out


def _open_setup(tmp_path, servers, docx_path=None, make_docx=True, record=None):
    home = make_home(tmp_path, "lecturer")
    ws, target = make_workspace(tmp_path, home, fixture="done.jsonl")
    docx = Path(docx_path) if docx_path else ws / "out" / "article.docx"
    if make_docx:
        docx.parent.mkdir(parents=True, exist_ok=True)
        docx.write_bytes(b"PK")
    target.write_text(target.read_text(encoding="utf-8").replace("/tmp/article.docx", str(docx)), encoding="utf-8")
    opened = []
    srv = servers(tmp_path, home, opener=lambda argv: opened.append(list(argv)))
    return srv, ws, docx, opened


def test_open_launches_only_the_recorded_docx(tmp_path, servers):
    srv, ws, docx, opened = _open_setup(tmp_path, servers)
    status, body = post(srv, "/api/open", {"run": "R", "workspace": str(ws)})
    assert status == 200 and body["ok"] is True
    assert len(opened) == 1 and opened[0][-1] == str(docx.resolve())
    assert opened[0][0] in ("open", "xdg-open")


def test_open_refuses_a_path_outside_every_workspace(tmp_path, servers):
    outside = tmp_path / "elsewhere" / "secret.docx"
    srv, ws, _, opened = _open_setup(tmp_path, servers, docx_path=outside)
    status, _ = post(srv, "/api/open", {"run": "R", "workspace": str(ws)})
    assert status in (400, 404) and opened == []


def test_open_refuses_a_symlink_escaping_the_workspace(tmp_path, servers):
    secret = tmp_path / "elsewhere" / "secret.docx"
    secret.parent.mkdir()
    secret.write_bytes(b"PK")
    home = make_home(tmp_path, "lecturer")
    ws, target = make_workspace(tmp_path, home, fixture="done.jsonl")
    link = ws / "link.docx"
    link.symlink_to(secret)
    target.write_text(target.read_text(encoding="utf-8").replace("/tmp/article.docx", str(link)), encoding="utf-8")
    opened = []
    srv = servers(tmp_path, home, opener=lambda argv: opened.append(argv))
    assert post(srv, "/api/open", {"run": "R", "workspace": str(ws)})[0] in (400, 404) and opened == []


def test_open_refuses_non_docx_and_missing_file(tmp_path, servers):
    srv, ws, docx, opened = _open_setup(tmp_path, servers)
    target = ws / ".academic-helper" / "runs" / "R" / "activity.jsonl"
    txt = ws / "notes.txt"
    txt.write_text("x")
    target.write_text(target.read_text(encoding="utf-8").replace(str(docx), str(txt)), encoding="utf-8")
    assert post(srv, "/api/open", {"run": "R", "workspace": str(ws)})[0] in (400, 404)  # nothing .docx recorded
    assert opened == []
    srv2, ws2, _, opened2 = _open_setup(tmp_path / "b", servers, make_docx=False)
    assert post(srv2, "/api/open", {"run": "R", "workspace": str(ws2)})[0] == 404 and opened2 == []


def test_open_refuses_unknown_run_workspace_and_bad_body(tmp_path, servers):
    srv, ws, _, opened = _open_setup(tmp_path, servers)
    assert post(srv, "/api/open", {"run": "nope", "workspace": str(ws)})[0] == 404
    assert post(srv, "/api/open", {"run": "R", "workspace": str(tmp_path / "unregistered")})[0] == 404
    assert post(srv, "/api/open", {"run": "../R", "workspace": str(ws)})[0] == 400
    assert post(srv, "/api/open", {"run": 5, "workspace": str(ws)})[0] == 400
    assert post(srv, "/api/open", {"run": "R"})[0] == 400
    assert opened == []
    assert post(srv, "/api/open", {"run": "R", "workspace": str(ws), "path": "/etc/passwd"})[0] == 200  # path ignored
    assert opened[-1][-1].endswith("article.docx")


def test_open_needs_origin_and_json(tmp_path, servers):
    srv, ws, _, opened = _open_setup(tmp_path, servers)
    assert post(srv, "/api/open", {"run": "R", "workspace": str(ws)}, origin="http://evil.example")[0] == 403
    assert post(srv, "/api/open", {"run": "R", "workspace": str(ws)}, origin=None)[0] == 403
    assert post(srv, "/api/open", {"run": "R", "workspace": str(ws)}, ctype="text/plain")[0] == 415
    assert opened == []


def test_default_opener_uses_an_argument_list_without_a_shell(monkeypatch):
    seen = {}

    def fake_popen(argv, **kw):
        seen["argv"], seen["kw"] = argv, kw

    monkeypatch.setattr(dashboard.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(dashboard.sys, "platform", "linux")
    dashboard.default_opener(["xdg-open", "/x/a b.docx"])
    assert seen["argv"] == ["xdg-open", "/x/a b.docx"] and not seen["kw"].get("shell")
    assert dashboard.opener_command(Path("/x/a.docx"), platform="darwin")[0] == "open"
    assert dashboard.opener_command(Path("/x/a.docx"), platform="linux")[0] == "xdg-open"
