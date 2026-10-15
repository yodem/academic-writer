"""End to end: the BUILT `aw library` with fake `trove` and `pilib` programs, in a temp research project.

Unit tests import src/ directly; this drives plugins/academic-writer/bin/aw, which is what ships. The fakes
are tiny Python scripts that answer the few commands the adapter uses, so no real library, host or account
is touched and no model is called. They are pointed at through the same settings a person would use
(AW_TROVE_COMMAND, AW_PAGEINDEX_COMMAND). Page text is identical on both routes, so agreement and support
can be asserted exactly.

Covered: route=trove (lookup rows only), route=both with an auditor-style read then verdict then report,
a failing and a hanging PageIndex shadow (the answering route's output must not change, and the report names
the shadow's trouble), and no library.json (same answers as Trove directly, plus a ledger row).
Every test removes the detached shadow workers it started.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import time

import pytest

jsonschema = pytest.importorskip("jsonschema")

ROOT = pathlib.Path(__file__).resolve().parent.parent
AW = ROOT / "plugins/academic-writer/bin/aw"
ROW_SCHEMA = json.loads((ROOT / "plugins/academic-writer/schemas/retrieval-row.schema.json").read_text(encoding="utf-8"))

# Same words as the book text the fakes serve: the auditor quote below is lifted from page 3 of "Book A".
PAGE = "the shared sentence number {n} about the long argument of this page"
QUOTE_P3 = "the shared sentence number 3 about the long argument"
# Words the second library's pages do not contain: the claim is not on the cited page (nor the one after it).
QUOTE_ELSEWHERE = "an entirely different claim concerning a quite distinct subject"

TROVE_FAKE = '''#!{python}
import json, os, sys
a = sys.argv[1:]
if os.environ.get("FAKE_LOG"):
    open(os.environ["FAKE_LOG"], "a").write("trove " + " ".join(a) + "\\n")
text = lambda n: "{page}".format(n=n)
if a[:1] == ["shelf"]:
    print("No active shelf")
elif a[:2] == ["items", "list"]:
    print(json.dumps({{"items": [{{"id": "T-A", "title": "Book A", "author": "Au", "pageCount": 5}}]}}))
elif a[:2] == ["items", "toc"] and "--json" in a:
    print(json.dumps({{"items": [{{"id": a[2], "title": "Book A", "toc": [{{"title": "Intro", "page": 1, "level": 1}}]}}]}}))
elif a[:2] == ["items", "toc"]:
    print("Book A\\nID: " + a[2])
elif a[:2] == ["items", "read"]:
    spec = a[a.index("--pages") + 1] if "--pages" in a else a[2].split(":")[1]
    ids = []
    for part in spec.split(","):
        low, _, high = part.partition("-")
        ids += range(int(low), int(high or low) + 1)
    sys.stdout.write("Book A\\n" + a[2].split(":")[0] + " | 5 pages\\n"
                     + "".join("\\u2500\\u2500 Page %d \\u2500\\u2500\\n%s\\n" % (n, text(n)) for n in ids if n <= 5))
else:
    sys.stderr.write("unexpected: " + " ".join(a) + "\\n")
    sys.exit(2)
'''

# MODE is baked in when the file is written: ok, fail (exit 1) or hang (never answers).
PILIB_FAKE = '''#!{python}
import json, os, sys, time
a = sys.argv[1:]
if os.environ.get("FAKE_LOG"):
    open(os.environ["FAKE_LOG"], "a").write("pilib " + " ".join(a) + "\\n")
MODE = "{mode}"
if MODE == "fail":
    sys.stderr.write("pilib: the index is unavailable\\n")
    sys.exit(1)
if MODE == "hang":
    # Handshake: say we started, then become a process that blocks and never finishes on its own. exec keeps the
    # pid, so killing the pid (or its group) stops the block; the tag in argv lets the test find it by name.
    open("{state}/pilib.started", "w").write(str(os.getpid()))
    os.execv(sys.executable, [sys.executable, "-c", "import time; time.sleep(600)", "{tag}"])
text = lambda n: "{page}".format(n=n)
if a[0] == "catalog":
    print(json.dumps({{"lib-a": {{"title": "Library A", "author": "Au", "n_pages": 5, "toc_source": "x", "top": []}}}}))
elif a[0] == "meta":
    print(json.dumps({{"book_id": a[1], "title": "Library A", "n_pages": 5, "origin": {{}}, "trove_id": "T-A", "pagemap": None}}))
elif a[0] == "tree":
    print(json.dumps({{"book_id": a[1], "title": "Library A", "n_pages": 5, "structure": []}}))
elif a[0] == "read":
    ids = []
    for part in a[2].split(","):
        low, _, high = part.partition("-")
        ids += range(int(low), int(high or low) + 1)
    print(json.dumps({{"book_id": a[1], "pages": [{{"page": n, "content": text(n)}} for n in ids if n <= 5]}}))
else:
    sys.stderr.write("unexpected: " + " ".join(a) + "\\n")
    sys.exit(2)
'''

SHADOW_TIMEOUT_MS = 6000  # the quiet second lookup is given up on after this; large so no assertion races it


class Project:
    """A temp research project plus the fake commands, and the way to run the built aw against it."""

    def __init__(self, root: pathlib.Path, pilib_mode: str = "ok", library: dict | None = None, with_shelf: bool = True):
        self.root = root
        self.project = root / "project"
        self.data = root / "data"
        self.log = root / "calls.log"
        bin_dir = root / "bin"
        bin_dir.mkdir(parents=True)
        self.helper = self.project / ".academic-helper"
        self.helper.mkdir(parents=True)
        self.data.mkdir()
        (self.helper / "profile.md").write_text("# profile\n", encoding="utf-8")
        # A printed page N is Trove page N + 1 in this fake book.
        (self.helper / "sources.json").write_text(json.dumps([
            {"sourceId": "T-A", "workTitle": "Book A", "pageMap": {"kind": "offset", "trove_minus_printed": 1}},
        ]), encoding="utf-8")
        if library is not None:
            (self.helper / "library.json").write_text(json.dumps(library), encoding="utf-8")
        if with_shelf:
            (self.project / "shelf.json").write_text(json.dumps({"map": {"T-A": {"book": "lib-a", "pages": "identity"}}}), encoding="utf-8")
        self.trove = self._write(bin_dir / "trove", TROVE_FAKE.format(python=sys.executable, page=PAGE))
        self.pilib = self._write(bin_dir / "pilib", PILIB_FAKE.format(python=sys.executable, mode=pilib_mode, page=PAGE, state=root, tag=root))
        self.env = {
            **{k: v for k, v in os.environ.items() if not k.startswith("AW_")},
            "AW_TROVE_COMMAND": str(self.trove),
            "AW_PAGEINDEX_COMMAND": str(self.pilib),
            "AW_LIBRARY_SHADOW_TIMEOUT_MS": str(SHADOW_TIMEOUT_MS),
            "FAKE_LOG": str(self.log),
        }

    @staticmethod
    def _write(path: pathlib.Path, body: str) -> pathlib.Path:
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
        return path

    def aw(self, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(AW), "--data-dir", str(self.data), "--project-dir", str(self.project), *args],
            capture_output=True, text=True, timeout=timeout, env=self.env,
        )

    def aw_json(self, *args: str) -> dict:
        p = self.aw(*args)
        assert p.returncode == 0, (args, p.stdout[-300:], p.stderr[-300:])
        return json.loads(p.stdout)

    def rows(self) -> list[dict]:
        file = self.helper / "retrieval.jsonl"
        if not file.exists():
            return []
        return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def wait_for(self, what: str, probe, timeout: float = 20.0):
        deadline = time.monotonic() + timeout
        while True:
            found = probe()
            if found:
                return found
            if time.monotonic() > deadline:
                pytest.fail(f"timed out waiting for {what}; ledger: {json.dumps(self.rows())[:600]}")
            time.sleep(0.05)

    def shadow_row(self, lookup_id: str) -> dict | None:
        return next((r for r in self.rows() if r["row_type"] == "shadow" and r["lookup_id"] == lookup_id), None)

    def leftovers(self) -> list[tuple[int, str]]:
        """Processes still running that belong to this project: every one has the project's unique temp folder in
        its command line (the detached shadow worker's spec path, the fake commands' script path, the tag the
        hanging fake carries after it execs). A ps that fails or does not even list this test is an error, never "clean"."""
        out = subprocess.run(["ps", "-axww", "-o", "pid=,command="], capture_output=True, text=True)
        if out.returncode != 0 or not re.search(rf"^\s*{os.getpid()}\s", out.stdout, flags=re.M):
            raise RuntimeError(f"ps could not list processes (exit {out.returncode}): {out.stderr[-200:]}")
        mine = []
        for line in out.stdout.splitlines():
            pid_text, _, command = line.strip().partition(" ")
            if pid_text.isdigit() and str(self.root) in command and int(pid_text) != os.getpid():
                mine.append((int(pid_text), command.strip()))
        return mine

    def kill_leftovers(self, deadline_s: float = 20.0) -> list[tuple[int, str]]:
        """Kill tagged processes (and their process groups), then look again, until two scans in a row find none
        or the deadline passes. A worker that starts a child after one scan is caught by the next scan. Returns what remains."""
        deadline = time.monotonic() + deadline_s
        clean_scans = 0
        while True:
            found = self.leftovers()
            if not found:
                clean_scans += 1
                if clean_scans >= 2:
                    return []
            else:
                clean_scans = 0
                for pid, _ in found:
                    try:
                        group = os.getpgid(pid)
                        if group != os.getpgrp():
                            os.killpg(group, signal.SIGKILL)
                        os.kill(pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
            if time.monotonic() > deadline:
                return self.leftovers()
            time.sleep(0.1)

    def started_pid(self) -> int | None:
        marker = self.root / "pilib.started"
        return int(marker.read_text()) if marker.exists() and marker.read_text().strip() else None


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.fixture(autouse=True)
def built_aw():
    if not AW.exists():
        pytest.fail("plugins/academic-writer/bin/aw is missing: run `npm run build` first")
    probe = subprocess.run([str(AW), "library", "status"], capture_output=True, text=True, timeout=30)
    if "expected aw library" in probe.stdout + probe.stderr or "unknown command" in (probe.stdout + probe.stderr).lower():
        pytest.fail("the built aw has no `library` command: run `npm run build`")


@pytest.fixture
def make_project(tmp_path):
    made: list[Project] = []

    def make(**kwargs) -> Project:
        project = Project(tmp_path / f"p{len(made)}", **kwargs)
        made.append(project)
        return project

    yield make
    # The detached shadow workers and any hanging fake command must not outlive the test, whatever happened in it.
    remaining = {project.root.name: project.kill_leftovers() for project in made}
    assert all(not left for left in remaining.values()), remaining


def assert_rows_valid(project: Project) -> None:
    for row in project.rows():
        jsonschema.validate(row, ROW_SCHEMA)


def only(rows: list[dict], row_type: str) -> list[dict]:
    return [r for r in rows if r["row_type"] == row_type]


def stable(read_output: dict) -> dict:
    """What the answering route returned, without the per-call ids, timing and route bookkeeping."""
    drop = {"lookup_id", "latency_ms", "mode", "shadow_status"}
    return {k: v for k, v in read_output.items() if k not in drop}


# ---------------------------------------------------------------------------------------------------------
# (1) route = trove


def test_route_trove_lists_reads_and_writes_lookup_rows_only(make_project):
    p = make_project(library={"route": "trove"})

    status = p.aw_json("library", "status")
    assert (status["route"], status["enabled"]) == ("trove", True)

    listed = p.aw_json("library", "list")
    assert [(b["id"], b["title"]) for b in listed["items"]] == [("T-A", "Book A")]

    toc = p.aw_json("library", "toc", "--source", "T-A")
    assert toc["toc"] and toc["toc"][0]["title"] == "Intro"

    read = p.aw_json("library", "read", "--source", "T-A", "--pages", "2-3")
    assert [e["trove_page"] for e in read["pages"]] == [2, 3]
    assert read["pages"][1]["text"] == PAGE.format(n=3)
    assert read["shadow_status"] == "none"

    rows = p.rows()
    assert {r["row_type"] for r in rows} == {"lookup"}
    assert [r["op"] for r in rows] == ["list", "toc", "read"]
    assert all(r["mode"] == "trove" and r["route_primary"] == "trove" and r["primary"]["ok"] for r in rows)
    assert_rows_valid(p)
    assert not [c for c in p.calls() if c.startswith("pilib")], "PageIndex must not be touched when route=trove"

    report = p.aw_json("library", "report", "--json")
    assert report["rows"] == {"lookup": 3, "shadow": 0, "verdict": 0, "invalid": 0}
    assert report["routes"]["trove"]["lookups"] == 3
    assert report["routes"]["pageindex"]["shadow_runs"] == 0


# ---------------------------------------------------------------------------------------------------------
# (2) route = both, Trove answers: an auditor-style read, verdict and report


def test_route_both_auditor_read_verdict_and_report(make_project):
    p = make_project(library={"route": "both", "primary": "trove", "pageindex": {"shelf": "shelf.json"}})
    run = "e2e-run"

    # The auditor reads by printed page (2 -> Trove page 3) for one paragraph, and passes it with a supporting quote.
    first = p.aw_json("library", "read", "--source", "T-A", "--printed", "2", "--run", run, "--claim", "P1")
    assert first["route"] == "trove" and first["shadow_status"] == "pending"
    assert first["request"]["trove_pages"] == "3"
    assert first["pages"][0]["text"] == PAGE.format(n=3)
    p.wait_for("the shadow of read 1", lambda: p.shadow_row(first["lookup_id"]))
    v1 = p.aw_json("library", "verdict", "--lookup", first["lookup_id"], "--verdict", "PASS",
                   "--support-quote", QUOTE_P3, "--paragraph", "P1", "--run", run)
    assert (v1["ok"], v1["verdict"], v1["shadow_supports"], v1["shadow_supports_reason"]) == (True, "PASS", True, "covered")

    # A second paragraph cites printed page 3 (Trove page 4) but the claim is elsewhere (page 5): FAIL with a corrected page.
    second = p.aw_json("library", "read", "--source", "T-A", "--printed", "3", "--run", run, "--claim", "P2")
    assert second["pages"][0]["trove_page"] == 4
    p.wait_for("the shadow of read 2", lambda: p.shadow_row(second["lookup_id"]))
    v2 = p.aw_json("library", "verdict", "--lookup", second["lookup_id"], "--verdict", "FAIL", "--corrected-page", "5",
                   "--support-quote", QUOTE_ELSEWHERE, "--paragraph", "P2", "--run", run)
    assert (v2["verdict"], v2["shadow_supports"]) == ("FAIL", False)

    rows = p.rows()
    assert_rows_valid(p)
    assert [r["op"] for r in only(rows, "lookup")] == ["read", "read"]
    assert {r["lookup_id"] for r in only(rows, "shadow")} == {first["lookup_id"], second["lookup_id"]}
    for shadow in only(rows, "shadow"):
        assert shadow["route"] == "pageindex" and shadow["ok"] and not shadow["timed_out"]
        assert shadow["agree"]["rate"] == 1 and shadow["agree"]["agreed"] == shadow["agree"]["compared"] == 1
    verdicts = {r["paragraph_id"]: r for r in only(rows, "verdict")}
    assert verdicts["P1"]["verdict"] == "PASS" and verdicts["P1"]["shadow_supports"] is True
    assert verdicts["P2"]["verdict"] == "FAIL" and verdicts["P2"]["corrected_page"] == 5 and verdicts["P2"]["shadow_supports"] is False

    report = p.aw_json("library", "report", "--run", run, "--json")
    assert report["rows"] == {"lookup": 2, "shadow": 2, "verdict": 2, "invalid": 0}
    trove = report["routes"]["trove"]
    assert trove["lookups"] == 2 and trove["errors"] == 0
    assert trove["auditor"]["pass"] == 1 and trove["auditor"]["fail"] == 1 and trove["auditor"]["pass_rate"] == 0.5
    assert trove["auditor"]["fail_with_corrected_page"] == 1
    assert (trove["auditor"]["shadow_checked"], trove["auditor"]["shadow_supports"]) == (2, 1)
    assert trove["agreement"] == {"pages_compared": 2, "pages_agreed": 2, "rate": 1}
    assert report["routes"]["pageindex"]["shadow_runs"] == 2
    assert report["routes"]["pageindex"]["shadow_errors"] == 0
    assert report["auditor"]["shadow_supports_by_verdict"]["PASS"]["supports"] == 1
    assert report["auditor"]["shadow_supports_by_verdict"]["FAIL"]["not_supports"] == 1
    assert report["auditor"]["lookups_with_verdict"] == report["auditor"]["read_lookups"] == 2

    text = p.aw("library", "report", "--run", run)
    assert text.returncode == 0
    assert "Auditor: 1 of 2 citations passed (50%)" in text.stdout
    assert "supported the claim for 1 of 2 checked (50%)" in text.stdout
    assert "Ran quietly alongside 2 times: 0 failed, 0 timed out" in text.stdout
    assert "the other library returned the same page text for 2 of 2 pages (100%)" in text.stdout

    assert any(c.startswith("pilib read") for c in p.calls()), "the quiet second lookup should have asked PageIndex"
    # The shadow workers have finished by now; nothing of ours is still running.
    p.wait_for("no leftover processes", lambda: not p.leftovers(), timeout=10)


# ---------------------------------------------------------------------------------------------------------
# (3) a failing and a hanging PageIndex shadow leave the answering route alone


def _baseline_read(make_project) -> dict:
    base = make_project(library={"route": "trove"})
    return stable(base.aw_json("library", "read", "--source", "T-A", "--pages", "2-4"))


def test_failing_shadow_leaves_primary_output_identical_and_report_shows_the_error(make_project):
    baseline = _baseline_read(make_project)
    p = make_project(pilib_mode="fail", library={"route": "both", "pageindex": {"shelf": "shelf.json"}})

    p.aw_json("library", "status")  # a no-op for the ledger; proves the config loads with a broken PageIndex
    read = p.aw_json("library", "read", "--source", "T-A", "--pages", "2-4", "--run", "fail-run")
    assert stable(read) == baseline
    assert read["shadow_status"] == "pending"

    shadow = p.wait_for("the failed shadow row", lambda: p.shadow_row(read["lookup_id"]))
    assert shadow["ok"] is False and shadow["timed_out"] is False
    assert "unavailable" in (shadow["error"] or "")
    assert_rows_valid(p)

    # The verdict is still recorded as the auditor gave it; there is just no second-library text to compare.
    verdict = p.aw_json("library", "verdict", "--lookup", read["lookup_id"], "--verdict", "PASS",
                        "--support-quote", QUOTE_P3, "--paragraph", "P1", "--run", "fail-run")
    assert verdict["ok"] is True and verdict["verdict"] == "PASS"
    assert verdict["shadow_supports"] is None and verdict["shadow_supports_reason"] == "shadow_missing"

    report = p.aw_json("library", "report", "--json")
    assert report["routes"]["trove"]["lookups"] == 1 and report["routes"]["trove"]["errors"] == 0
    assert report["routes"]["pageindex"]["shadow_runs"] == 1 and report["routes"]["pageindex"]["shadow_errors"] == 1
    assert report["routes"]["pageindex"]["shadow_timeouts"] == 0
    assert report["data_quality"]["shadow_missing_verdicts"] == 1
    assert "1 failed, 0 timed out" in p.aw("library", "report").stdout
    p.wait_for("no leftover processes", lambda: not p.leftovers(), timeout=10)


def test_hanging_shadow_never_delays_the_primary_and_the_report_shows_a_timeout(make_project):
    baseline = _baseline_read(make_project)
    p = make_project(pilib_mode="hang", library={"route": "both", "pageindex": {"shelf": "shelf.json"}})

    # The primary command runs to completion (aw_json asserts exit 0 and parses its output) with the right answer.
    read = p.aw_json("library", "read", "--source", "T-A", "--pages", "2-4", "--run", "hang-run")
    assert stable(read) == baseline
    assert read["shadow_status"] == "pending"

    # Handshake, no clock: the fake pilib records that it started and then blocks for good. Whenever it started,
    # aw had already exited, so the answer never waited for it; and it is still blocked now.
    p.wait_for("the fake pilib to start", p.started_pid)
    pilib_pid = p.started_pid()
    assert pilib_pid is not None and alive(pilib_pid), "the hanging pilib must still be blocked after the primary returned"

    # Later, the shadow gives up on its own time limit: a ledger row, not a failure of the lookup.
    shadow = p.wait_for("the timed-out shadow row", lambda: p.shadow_row(read["lookup_id"]), timeout=60)
    assert shadow["ok"] is False and shadow["timed_out"] is True
    assert_rows_valid(p)

    report = p.aw_json("library", "report", "--json")
    assert report["routes"]["trove"]["errors"] == 0
    assert report["routes"]["pageindex"]["shadow_timeouts"] == 1
    assert "1 timed out" in p.aw("library", "report").stdout
    # The timed-out worker took its blocked pilib down with it.
    p.wait_for("the blocked pilib to be stopped", lambda: not alive(pilib_pid), timeout=30)
    p.wait_for("no leftover processes", lambda: not p.leftovers(), timeout=30)


# ---------------------------------------------------------------------------------------------------------
# (4) no library.json: the same answers as Trove directly, plus a lookup row


def _direct_trove_pages(p: Project, pages: str) -> list[tuple[int, str]]:
    out = subprocess.run([str(p.trove), "items", "read", "T-A", "--pages", pages], capture_output=True, text=True, check=True).stdout
    found = re.findall(r"── Page (\d+) ──\n(.*?)(?=\n── Page |\Z)", out, flags=re.S)
    return [(int(n), text.strip()) for n, text in found]


def test_without_library_json_answers_match_trove_directly_and_a_lookup_row_is_written(make_project):
    p = make_project(library=None, with_shelf=False)
    assert not (p.helper / "library.json").exists()

    status = p.aw_json("library", "status")
    assert (status["route"], status["configured"], status["enabled"]) == ("trove", False, True)

    direct_list = json.loads(subprocess.run([str(p.trove), "items", "list", "--json"], capture_output=True, text=True, check=True).stdout)["items"]
    listed = p.aw_json("library", "list")
    assert listed["items"] == direct_list

    read = p.aw_json("library", "read", "--source", "T-A", "--pages", "2-4")
    assert [(e["trove_page"], e["text"]) for e in read["pages"]] == _direct_trove_pages(p, "2-4")
    assert read["shadow_status"] == "none"

    rows = p.rows()
    assert [r["op"] for r in rows] == ["list", "read"]
    assert {r["row_type"] for r in rows} == {"lookup"}
    assert all(r["mode"] == "trove" and r["primary"]["ok"] for r in rows)
    assert rows[1]["source_id"] == "T-A" and rows[1]["request"]["trove_pages"] == "2-4"
    assert_rows_valid(p)
    assert not [c for c in p.calls() if c.startswith("pilib")]
    assert not (p.helper / "library.json").exists(), "reading must not create a route choice"

    report = p.aw_json("library", "report", "--json")
    assert report["rows"]["lookup"] == 2 and report["rows"]["shadow"] == 0
    assert "No lookups" not in p.aw("library", "report").stdout
