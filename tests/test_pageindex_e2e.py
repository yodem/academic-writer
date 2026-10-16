"""End to end: PageIndex built into `aw library`, driven through the real program with fakes only.

`tests/_awbuild.py` bundles src/cli into a temporary plugin folder (it never reads the committed `plugins/`), so this
file passes on a clean checkout. Everything outside the program under test is a small stand-in written here:

- a fake `trove` command that serves books from a folder (read-only: any write command is refused and logged),
- a stub `litellm` module (no model, no network; it records each call and which key it saw),
- a fake `claude` command that plays the locating agent of a blind evaluation, from a script,
- a stand-in for the built-in helper's private Python (a two-line shell program that adds the stub), and a wrapper
  command, both in front of the REAL pilib from src/scripts/pageindex.

Covered: routes trove | pageindex | both against the installed command and against a wrapper command; `aw library
index --trove-id` for a new item and for an existing item (re-index, with read-back); backfill of two books; the
report (estimated tokens, latency, cost, auditor PASS rate, page agreement, shadow supports); a full blind evaluation
round (plan, run, pairs, page, import of a scripted judgments file, unblind with exact win rates, and no route name in
anything the judge sees); which keys each command receives (every invocation dumps its own environment to a file, and
the test reads those files); and no process left behind by any test (looked for before the teardown kills anything).

Waiting is done with handshakes (a file appears, a ledger row appears), never with a clock that races a timeout.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _awbuild import ROOT, bundle_aw, clean_env, make_plugin_folder  # noqa: E402

jsonschema = pytest.importorskip("jsonschema")

ROW_SCHEMA = json.loads((ROOT / "src/schemas/retrieval-row.schema.json").read_text(encoding="utf-8"))
PINNED = json.loads((ROOT / "src/scripts/pageindex/PINNED.json").read_text(encoding="utf-8"))

PLUGIN_KEY = "test-plugin-key-aaaa1111"   # the key the plugin holds (GOOGLE_API_KEY): only the built-in helper may get it
SERVER_KEY = "test-server-key-bbbb2222"   # the key a wrapper's own computer holds
# Other secrets the researcher's shell holds. None of them may reach a command the plugin starts (the built-in helper gets the
# plugin's key as GEMINI_API_KEY while it writes summaries, and nothing else). GEMINI_API_KEY here differs from the plugin's
# key, so a command that received it would show up even where the plugin's own key was replaced.
PARENT_GEMINI_KEY = "test-parent-gemini-cccc3333"
ANTHROPIC_KEY = "test-anthropic-key-dddd4444"
JEV_KEY = "test-jev-key-eeee5555"
OPENAI_KEY = "test-openai-key-ffff6666"
GITHUB_TOKEN = "test-github-token-gggg7777"
AWS_SECRET = "test-aws-secret-hhhh8888"
PARENT_SECRETS = {"GOOGLE_API_KEY": PLUGIN_KEY, "GEMINI_API_KEY": PARENT_GEMINI_KEY, "ANTHROPIC_API_KEY": ANTHROPIC_KEY, "JEV_API_KEY": JEV_KEY,
                  "OPENAI_API_KEY": OPENAI_KEY, "GITHUB_TOKEN": GITHUB_TOKEN, "AWS_SECRET_ACCESS_KEY": AWS_SECRET}
ALL_KEYS = (PLUGIN_KEY, SERVER_KEY, PARENT_GEMINI_KEY, ANTHROPIC_KEY, JEV_KEY, OPENAI_KEY, GITHUB_TOKEN, AWS_SECRET)
SHADOW_TIMEOUT_MS = 120_000               # far above any scheduling delay: no test races it
ROUTE_WORDS = re.compile(r"trove|page-?index", re.IGNORECASE)

# ---------------------------------------------------------------------------------------------------------
# The books of the fake Trove. Every page says what it is about, so a claim can be located on exactly one page.

TOPICS = {
    "alpha": ["a guide for the reader", "the written text and its plain sense", "monetary compensation for injury",
              "the oral tradition and its chain", "the authority of the sages", "the court of three judges",
              "the testimony of two witnesses", "a glossary of legal terms"],
    "beta": ["the first principles of trade", "weights and measures in the market", "interest and the lender",
             "partnership between two traders", "hired workers and their wages", "a note on later custom"],
    "gamma": ["the calendar and the new moon", "the festival of the harvest", "the fast and its purpose",
              "the rules of the sabbath rest", "carrying between two domains", "lights and their kindling",
              "a summary of the order"],
}
LATER_TOPICS = {"alpha": ["later rulings"]}  # a page the reader adds to the Trove item in the re-index test
TITLES = {"alpha": "Alpha Volume on Law", "beta": "Beta Volume on Trade", "gamma": "Gamma Volume on Time"}
TOCS = {
    "alpha": [("Reading guide - How to read this volume.", 1, 1), ("Part one - The sources of law.", 2, 1),
              ("Chapter 1 - The written text and its plain sense.", 2, 2), ("Chapter 2 - The oral tradition and its authority.", 4, 2),
              ("Part two - Practice in court.", 6, 1), ("Chapter 3 - Judges and witnesses.", 6, 2), ("Appendix - Glossary of terms.", 8, 1)],
    "beta": [("Part one - Trade.", 1, 1), ("Chapter 1 - Weights and interest.", 2, 2),
             ("Part two - Work.", 4, 1), ("Chapter 2 - Partners and wages.", 4, 2)],
    "gamma": [("Part one - The year.", 1, 1), ("Chapter 1 - The calendar and the festivals.", 1, 2),
              ("Part two - The sabbath.", 4, 1), ("Chapter 2 - Rest and carrying.", 4, 2), ("Summary - The order.", 7, 1)],
}
FLAT_TOC = [(f"Page {n}", n, 1) for n in range(1, 5)]  # no hints: such a book needs the structure helper


def page_text(book: str, number: int) -> str:
    """The text of one page: a heading line, then a sentence that names the page's topic."""
    topic = (TOPICS[book] + LATER_TOPICS.get(book, []))[number - 1] if book in TOPICS else f"flat page {number}"
    return f"# {TITLES.get(book, book)}, page {number}\n\nThis page deals with {topic}, with an example and a short objection."


def book_json(book: str, toc=None, pages: int | None = None) -> dict:
    count = pages if pages is not None else len(TOPICS[book])
    return {
        "title": TITLES.get(book, "A Flat Book"), "author": "Test Author",
        "toc": [{"title": t, "page": p, "level": l} for t, p, l in (toc if toc is not None else TOCS[book])],
        "pages": [{"pageNum": n, "content": page_text(book, n) if book in TOPICS or book == "flat" else f"# {book} page {n}"} for n in range(1, count + 1)],
    }


# ---------------------------------------------------------------------------------------------------------
# The stand-ins (plain scripts written into a temp folder; @@NAME@@ marks what is filled in)

FAKE_TROVE = '''#!@@PYTHON@@
import json, os, sys
args = [a for a in sys.argv[1:] if a != "--no-session"]
DATA = "@@DATA@@"
if os.environ.get("FAKE_LOG"):
    open(os.environ["FAKE_LOG"], "a").write("trove " + " ".join(sys.argv[1:]) + "\\n")

def load(book_id):
    path = os.path.join(DATA, book_id + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None

if args[:2] == ["shelf", "current"]:
    print("No active shelf")
elif args[:2] == ["items", "list"]:
    ids = sorted(f[:-5] for f in os.listdir(DATA) if f.endswith(".json"))
    print(json.dumps({"items": [{"id": i, "title": load(i)["title"], "author": load(i)["author"], "pageCount": len(load(i)["pages"])} for i in ids]}))
elif args[:2] == ["items", "toc"] and len(args) >= 3:
    book = load(args[2])
    if book is None:
        sys.stderr.write("no such item " + args[2] + "\\n"); sys.exit(1)
    if "--json" in args:
        print(json.dumps({"items": [{"id": args[2], "title": book["title"], "author": book["author"], "toc": book["toc"]}]}, ensure_ascii=False))
    else:
        print(book["title"] + "\\nID: " + args[2])
elif args[:2] == ["items", "read"] and len(args) >= 3:
    book_id, _, spec = args[2].partition(":")
    if "--pages" in args:
        spec = args[args.index("--pages") + 1]
    book = load(book_id)
    if book is None:
        sys.stderr.write("no such item " + book_id + "\\n"); sys.exit(1)
    if "--json" in args and spec == "all":
        print(json.dumps({"items": [{"id": book_id, "title": book["title"], "pages": book["pages"]}]}, ensure_ascii=False))
    else:
        ids = []
        for part in spec.split(","):
            low, _, high = part.partition("-")
            ids += range(int(low), int(high or low) + 1)
        by_number = {p["pageNum"]: p["content"] for p in book["pages"]}
        sys.stdout.write(book["title"] + "\\n" + book_id + " | " + str(len(by_number)) + " pages\\n"
                         + "".join("\\u2500\\u2500 Page %d \\u2500\\u2500\\n%s\\n" % (n, by_number[n]) for n in ids if n in by_number))
else:
    sys.stderr.write("fake trove: this call is not allowed here: " + " ".join(args) + "\\n")
    sys.exit(2)
'''

# `import litellm` finds this file first. It records every call (never the key itself) and answers with a short summary.
STUB_LITELLM = '''import hashlib, json, os, sys, types
suppress_debug_info = False
PLUGIN_KEY, SERVER_KEY = "@@PLUGIN_KEY@@", "@@SERVER_KEY@@"

def completion(*args, model=None, messages=None, **kwargs):
    prompt = messages[0]["content"]
    key = os.environ.get("GEMINI_API_KEY", "")
    if os.environ.get("FAKE_LITELLM_LOG"):
        open(os.environ["FAKE_LITELLM_LOG"], "a").write(json.dumps({
            "model": model, "prompt_chars": len(prompt),
            "key": "plugin" if key == PLUGIN_KEY else "server" if key == SERVER_KEY else "none" if not key else "other",
            "key_in_argv": any(PLUGIN_KEY in a or SERVER_KEY in a for a in sys.argv),
        }) + "\\n")
    text = "Summary " + hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8] + " of the section."
    usage = types.SimpleNamespace(prompt_tokens=120, completion_tokens=30, completion_tokens_details=types.SimpleNamespace(reasoning_tokens=0))
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=text))], usage=usage)

async def acompletion(*args, **kwargs):
    return completion(*args, **kwargs)

def completion_cost(completion_response=None):
    return 0.002
'''

# What the plugin's private Python is: the real interpreter with the stub litellm in front.
# Every invocation first writes its own full environment (and its arguments) to a file of its own, so a test can read what the
# command really received. The dump folder is baked into the script, not passed in the environment, so it works whatever the
# program under test hands down.
VENV_PYTHON = '''#!/bin/sh
{ printf 'ARGS: %s\\n' "$(echo "$*" | tr '\\n' ' ')"; env; } > "$(mktemp '@@DUMPS@@/helper.XXXXXX')"
PYTHONPATH='@@STUBS@@'"${PYTHONPATH:+:$PYTHONPATH}"; export PYTHONPATH
exec '@@PYTHON@@' "$@"
'''

# A command the researcher supplies: it runs pilib for a library of its own, with its own key and its own `trove`.
WRAPPER = '''#!/bin/sh
{ printf 'ARGS: %s\\n' "$(echo "$*" | tr '\\n' ' ')"; env; } > "$(mktemp '@@DUMPS@@/wrapper.XXXXXX')"
GEMINI_API_KEY='@@SERVER_KEY@@'; export GEMINI_API_KEY
AW_LIBRARY='@@LIBRARY@@'; export AW_LIBRARY
PATH='@@BIN@@':"$PATH"; export PATH
PYTHONPATH='@@STUBS@@:@@SOURCE@@'; export PYTHONPATH
exec '@@PYTHON@@' -m pilib "$@"
'''

# The locating agent of the evaluation. It reads the prompt on stdin, learns which library its wrapper stands for from the
# wrapper file itself (a test double may peek; the real agent cannot), runs the table of contents and one read through the
# wrapper like the real agent would, and prints stream-json events. FAKE_CLAUDE_SCRIPT holds the answers.
FAKE_CLAUDE = '''#!@@PYTHON@@
import json, os, re, shlex, subprocess, sys, time
prompt = sys.stdin.read()
script = json.load(open(os.environ["FAKE_CLAUDE_SCRIPT"], encoding="utf-8"))
wrapper = re.search(r"^(\\S+) toc --source", prompt, re.M).group(1)
claim = re.search(r'Claim from the article:\\n"(.*)"', prompt).group(1)
route = re.search(r"AW_LIBRARY_ROUTE='(\\w+)'", open(wrapper, encoding="utf-8").read()).group(1)
entry = next(v for k, v in script["answers"].items() if k in claim)
answer = entry[route]
events = [{"type": "system", "subtype": "init", "model": "fake-claude", "claude_code_version": "0.0.0-test"}]
calls = ["%s toc --source %s" % (wrapper, answer["book"]),
         "%s read --source %s --pages %d --text" % (wrapper, answer["book"], answer["pages"][0])]
for number, call in enumerate(calls):
    done = subprocess.run(shlex.split(call), capture_output=True, text=True)
    events.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t%d" % number, "name": "Bash", "input": {"command": call}}]}})
    events.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t%d" % number, "content": done.stdout[:200], "is_error": done.returncode != 0}]}})
tokens = script["usage"][route]
final = "Found it.\\n```json\\n" + json.dumps({"book": answer["book"], "pages": answer["pages"], "reason": "the page names the topic"}) + "\\n```"
events.append({"type": "result", "subtype": "success", "is_error": False, "result": final, "num_turns": 3, "duration_ms": tokens["duration_ms"],
               "total_cost_usd": tokens["cost_usd"], "usage": {"input_tokens": tokens["input"], "output_tokens": tokens["output"]}, "permission_denials": []})
for event in events:
    print(json.dumps(event))
sys.stdout.flush()
if os.environ.get("FAKE_CLAUDE_LINGER"):
    # Leave a blocker behind in a session of its own, tagged with this test's folder in its command line: only the runner's
    # cleanup (by the run tag or by following the process tree) can stop it before the test's own teardown does.
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)", os.environ["FAKE_CLAUDE_LINGER"]],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    open(os.environ["FAKE_CLAUDE_LINGER_PID"] + "." + str(os.getpid()), "w").write(str(child.pid))
'''


def fill(template: str, **values: str) -> str:
    out = template
    for name, value in values.items():
        out = out.replace(f"@@{name}@@", value)
    assert "@@" not in out, out[:200]
    return out


# ---------------------------------------------------------------------------------------------------------
# The world of one test: plugin folder, fakes, project, data folder, and the way to run the bundled aw.


class World:
    def __init__(self, root: pathlib.Path, aw_bundle: pathlib.Path, library_json: dict | None = None, books=("alpha", "beta", "gamma"),
                 installed: bool = True, golden: pathlib.Path | None = None):
        self.root = root
        root.mkdir(parents=True)
        self.plugin = make_plugin_folder(root / "plugin", aw_bundle)
        self.aw_path = self.plugin / "bin" / "aw"
        self.bin = root / "bin"
        self.bin.mkdir()
        self.stubs = root / "stubs"
        self.stubs.mkdir()
        self.trove_data = root / "trove-data"
        self.trove_data.mkdir()
        self.project = root / "project"
        self.helper = self.project / ".academic-helper"
        self.helper.mkdir(parents=True)
        self.data = root / "data"
        self.data.mkdir()
        self.home = self.data / "pageindex"          # where the built-in helper lives
        self.library = self.home / "library"
        self.trove_log = root / "trove.log"
        self.litellm_log = root / "litellm.log"
        self.dumps = root / "env-dumps"               # one file per invocation of the helper or of the wrapper
        self.dumps.mkdir()
        self.seen: dict[int, str] = {}                # every process of this test seen by leftovers(), by pid
        self.stub_python = (self.stubs / "bin")
        (self.helper / "profile.md").write_text("# profile\n", encoding="utf-8")
        self.trove = self._script(self.bin / "trove", fill(FAKE_TROVE, PYTHON=sys.executable, DATA=str(self.trove_data)))
        (self.stubs / "litellm.py").write_text(fill(STUB_LITELLM, PLUGIN_KEY=PLUGIN_KEY, SERVER_KEY=SERVER_KEY), encoding="utf-8")
        for book in books:
            self.set_book(book, book_json(book))
        if library_json is not None:
            (self.helper / "library.json").write_text(json.dumps(library_json), encoding="utf-8")
        self.env = clean_env(
            PATH=f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}",
            AW_TROVE_COMMAND=str(self.trove),
            AW_LIBRARY_SHADOW_TIMEOUT_MS=str(SHADOW_TIMEOUT_MS),
            AW_E2E_TAG=str(root),                          # the marker every process of this test carries in its environment
            **PARENT_SECRETS,
            FAKE_LOG=str(self.trove_log),
            FAKE_LITELLM_LOG=str(self.litellm_log),
        )
        if installed:
            self.install_helper(golden)

    # ---- the fakes ----

    @staticmethod
    def _script(path: pathlib.Path, body: str) -> pathlib.Path:
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
        return path

    def set_book(self, book_id: str, document: dict) -> None:
        (self.trove_data / f"{book_id}.json").write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    def install_helper(self, golden: pathlib.Path | None) -> None:
        """What `aw library install` leaves behind, without pip: the record, the private Python (the real interpreter with the
        stub litellm in front of it) and, optionally, a library copied from a prebuilt one. The pilib source is the plugin's own."""
        core = PINNED["tiers"]["core"]
        (self.home / "venv" / "bin").mkdir(parents=True, exist_ok=True)
        self._script(self.home / "venv" / "bin" / "python", fill(VENV_PYTHON, STUBS=str(self.stubs), PYTHON=sys.executable, DUMPS=str(self.dumps)))
        (self.home / "installed.json").write_text(json.dumps({
            "schema": 1, "tier": "core", "python": sys.version.split()[0], "pageindex_commit": None,
            "requirements_sha256": core["requirements_sha256"], "pilib_version": PINNED["pilib_version"],
            "litellm": core["litellm"], "installed_at": "2026-10-16T00:00:00Z",
        }), encoding="utf-8")
        self.library.mkdir(parents=True, exist_ok=True)
        if golden is not None:
            shutil.copytree(golden, self.library, dirs_exist_ok=True)
        self.env["AW_PAGEINDEX_HOME"] = str(self.home)

    def make_wrapper(self, library: pathlib.Path | None = None) -> pathlib.Path:
        """A command of the researcher's own (a stand-in for an ssh wrapper to another computer), with a library folder of its own."""
        library = library or (self.root / "server-library")
        library.mkdir(parents=True, exist_ok=True)
        return self._script(self.bin / "pageindex-wrapper", fill(
            WRAPPER, SERVER_KEY=SERVER_KEY, LIBRARY=str(library), BIN=str(self.bin), STUBS=str(self.stubs),
            SOURCE=str(self.plugin / "scripts" / "pageindex"), PYTHON=sys.executable, DUMPS=str(self.dumps)))

    def set_library_json(self, config: dict) -> None:
        (self.helper / "library.json").write_text(json.dumps(config), encoding="utf-8")

    # ---- running aw ----

    def aw(self, *args: str, env: dict | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run([str(self.aw_path), "--data-dir", str(self.data), "--project-dir", str(self.project), *args],
                              capture_output=True, text=True, timeout=timeout, env={**self.env, **(env or {})}, cwd=str(self.project))

    def aw_json(self, *args: str, env: dict | None = None, expect: int = 0) -> dict:
        done = self.aw(*args, env=env)
        assert done.returncode == expect, (args, done.returncode, done.stdout[-500:], done.stderr[-500:])
        return json.loads(done.stdout.strip().splitlines()[-1])

    # ---- what the program left behind ----

    def rows(self) -> list[dict]:
        file = self.helper / "retrieval.jsonl"
        return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.strip()] if file.exists() else []

    def usage_rows(self) -> list[dict]:
        """Every usage row of the project. The order is NOT meaningful (run folders are named by a one-second timestamp plus a
        random suffix, and a row carries no time): pick rows by `run_id` with `usage_of`, or compare them as a whole."""
        rows = []
        for file in sorted((self.helper / "runs").glob("*/usage.jsonl")) if (self.helper / "runs").exists() else []:
            rows += [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]
        return rows

    def usage_of(self, run_id: str, step: str = "library.index") -> dict:
        """The one usage row of a run, found by the run id the program printed for it."""
        rows = [r for r in self.usage_rows() if r["run_id"] == run_id and r["step"] == step]
        assert len(rows) == 1, (run_id, step, rows)
        return rows[0]

    def trove_calls(self) -> list[str]:
        return self.trove_log.read_text(encoding="utf-8").splitlines() if self.trove_log.exists() else []

    def litellm_calls(self) -> list[dict]:
        return [json.loads(line) for line in self.litellm_log.read_text(encoding="utf-8").splitlines()] if self.litellm_log.exists() else []

    def shadow_row(self, lookup_id: str) -> dict | None:
        return next((r for r in self.rows() if r["row_type"] == "shadow" and r["lookup_id"] == lookup_id), None)

    def wait_for(self, what: str, probe, timeout: float = 60.0):
        deadline = time.monotonic() + timeout
        while True:
            found = probe()
            if found:
                return found
            if time.monotonic() > deadline:
                pytest.fail(f"timed out waiting for {what}; ledger: {json.dumps(self.rows())[:600]}")
            time.sleep(0.05)

    def assert_rows_valid(self) -> None:
        for row in self.rows():
            jsonschema.validate(row, ROW_SCHEMA)

    # ---- processes: every one of ours has this test's unique folder in its command line ----

    def leftovers(self) -> list[tuple[int, str]]:
        """The processes of this test that are alive now, and every one of them is remembered in `self.seen`. A process is ours if
        its command line or (ps prints it after the command) its environment names this test's folder: the helper's Python is
        an exec of the real interpreter whose command line does not, but it carries AW_E2E_TAG like everything aw starts."""
        out = subprocess.run(["ps", "axwwE" if sys.platform == "darwin" else "axwwe", "-o", "pid=,command="], capture_output=True, text=True)
        if out.returncode != 0 or not re.search(rf"^\s*{os.getpid()}\s", out.stdout, flags=re.M):
            raise RuntimeError(f"ps could not list processes (exit {out.returncode}): {out.stderr[-200:]}")
        mine_pattern = re.compile(re.escape(str(self.root)) + r"(?!\w)")
        mine = []
        for line in out.stdout.splitlines():
            pid_text, _, command = line.strip().partition(" ")
            if pid_text.isdigit() and mine_pattern.search(command) and int(pid_text) != os.getpid():
                mine.append((int(pid_text), command.strip()[:300]))
                self.seen[int(pid_text)] = command.strip()[:300]
        return mine

    def kill_leftovers(self, deadline_s: float = 20.0) -> list[tuple[int, str]]:
        """Kill what is tagged (and its process group), then look again until two scans in a row find nothing: a worker
        that starts a child after one scan is caught by the next one. Returns what remains at the deadline."""
        deadline = time.monotonic() + deadline_s
        clean = 0
        while True:
            found = self.leftovers()
            if not found:
                clean += 1
                if clean >= 2:
                    return []
            else:
                clean = 0
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

    def all_text(self) -> str:
        """Everything the program wrote under the project and the data folder, as text (for the key checks)."""
        parts = []
        for base in (self.project, self.data):
            for path in base.rglob("*"):
                if path.is_file() and path.stat().st_size < 5_000_000:
                    try:
                        parts.append(path.read_text(encoding="utf-8"))
                    except (UnicodeDecodeError, OSError):
                        pass
        return "\n".join(parts)


@pytest.fixture(scope="session")
def aw_bundle(tmp_path_factory) -> pathlib.Path:
    return bundle_aw(tmp_path_factory.mktemp("aw-bundle"))


@pytest.fixture(scope="session")
def golden_library(aw_bundle, tmp_path_factory) -> pathlib.Path:
    """A PageIndex library with alpha, beta and gamma indexed (summaries from the stub), built once through aw itself."""
    world = World(tmp_path_factory.mktemp("golden") / "w", aw_bundle)
    done = world.aw_json("library", "backfill", "--ids", "alpha,beta,gamma", "--yes")
    assert done["ok"] and done["indexed"] == 3, done
    survivors = world.leftovers()
    assert world.kill_leftovers() == [] and survivors == [], f"the backfill left processes running: {survivors}"
    return world.library


@pytest.fixture
def make_world(tmp_path, aw_bundle, golden_library):
    made: list[World] = []

    def make(prebuilt: bool = True, **kwargs) -> World:
        """`prebuilt`: the built-in helper starts with alpha, beta and gamma already indexed; False starts it with an empty library."""
        world = World(tmp_path / f"w{len(made)}", aw_bundle, golden=golden_library if prebuilt else None, **kwargs)
        made.append(world)
        return world

    yield make
    # First look BEFORE anything is killed: a program that leaves a process behind must fail its test even though the cleanup
    # below would stop it. Then clean up in every case (a leak must not outlive the test), and look again.
    survivors = {world.root.name: world.leftovers() for world in made}
    remaining = {world.root.name: world.kill_leftovers() for world in made}
    assert all(not left for left in survivors.values()), f"processes still running when the test ended (killed by the teardown): {survivors}"
    assert all(not left for left in remaining.values()), f"processes the teardown could not stop: {remaining}"


def only(rows: list[dict], row_type: str) -> list[dict]:
    return [r for r in rows if r["row_type"] == row_type]


def assert_no_secret_anywhere(world: World, *outputs: str) -> None:
    text = "\n".join(outputs) + "\n" + world.all_text() + "\n" + "\n".join(world.trove_calls())
    for secret in ALL_KEYS:
        assert secret not in text, "a key leaked into an output, a ledger or a file"


# ---------------------------------------------------------------------------------------------------------
# (1) Routes: trove | pageindex | both, against the installed command and against a wrapper command

KINDS = ["installed", "wrapper"]
ROUTES = ["trove", "pageindex", "both"]


@pytest.fixture
def wrapper_world(make_world, golden_library):
    """A project whose PageIndex command is a wrapper (no built-in helper installed), over a library the wrapper holds."""
    def make(route: str) -> World:
        world = make_world(library_json=None, installed=False)
        wrapper = world.make_wrapper(world.root / "server-library")
        shutil.copytree(golden_library, world.root / "server-library", dirs_exist_ok=True)
        world.set_library_json({"route": route, "pageindex": {"command": [str(wrapper)]}})
        return world
    return make


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("kind", KINDS)
def test_routes_answer_the_same_pages_through_both_kinds_of_command(kind, route, make_world, wrapper_world):
    world = make_world(library_json={"route": route}) if kind == "installed" else wrapper_world(route)
    expected_secondary = {"trove": None, "pageindex": None, "both": "pageindex"}[route]
    primary = "pageindex" if route == "pageindex" else "trove"

    status = world.aw_json("library", "status")
    assert (status["route"], status["primary"], status["secondary"]) == (route, primary, expected_secondary)
    assert status["pageindex_source"] == ("installed" if kind == "installed" else "library.json")
    if kind == "installed":
        assert status["installed"]["installed"] is True and status["installed"]["matches_pinned"] is True

    listed = world.aw_json("library", "list", "--run", "r1")
    assert listed["route"] == primary
    assert sorted(b["id"] for b in listed["items"]) == ["alpha", "beta", "gamma"]

    toc = world.aw_json("library", "toc", "--source", "alpha", "--run", "r1")
    assert toc["route"] == primary
    assert sorted(e["page"] for e in toc["toc"]) == sorted(p for _, p, _ in TOCS["alpha"])

    read = world.aw_json("library", "read", "--source", "alpha", "--pages", "2-4", "--run", "r1", "--claim", "P1")
    assert read["route"] == primary and read["mode"] == route
    assert [(e["trove_page"], e["text"]) for e in read["pages"]] == [(n, page_text("alpha", n)) for n in (2, 3, 4)]
    assert read["missing_pages"] == []
    assert read["shadow_status"] == ("pending" if route == "both" else "none")

    rows = world.rows()
    assert [r["op"] for r in only(rows, "lookup")] == ["list", "toc", "read"]
    assert all(r["mode"] == route and r["route_primary"] == primary and r["primary"]["ok"] for r in only(rows, "lookup"))
    # Tokens are labelled estimates, and a page read says how many distinct pages came back.
    read_row = only(rows, "lookup")[2]
    assert read_row["primary"]["tokens_basis"] == "estimate" and read_row["primary"]["est_tokens"] > 0
    assert read_row["primary"]["pages_returned"] == 3

    if route == "both":
        # Every lookup has a quiet second lookup on the other library; for the read, the pages are the same text.
        for lookup in only(world.rows(), "lookup"):
            shadow = world.wait_for(f"the shadow of {lookup['op']}", lambda i=lookup["lookup_id"]: world.shadow_row(i))
            assert shadow["route"] == "pageindex" and shadow["ok"] and not shadow["timed_out"]
        read_shadow = world.shadow_row(read["lookup_id"])
        assert read_shadow["agree"]["compared"] == 3 and read_shadow["agree"]["agreed"] == 3 and read_shadow["agree"]["rate"] == 1
        assert read_shadow["est_tokens"] > 0
    else:
        assert not only(world.rows(), "shadow")
    world.assert_rows_valid()

    # Whichever library answers, the whole book reads back the same text, page by page.
    full = world.aw_json("library", "read", "--source", "alpha", "--pages", "1-8")
    assert [e["text"] for e in full["pages"]] == [page_text("alpha", n) for n in range(1, 9)]
    if route == "both":
        world.wait_for("no leftover processes", lambda: not world.leftovers(), timeout=30)
    assert_no_secret_anywhere(world, json.dumps(read), json.dumps(status))


def test_forced_route_overrides_library_json_and_a_typo_is_refused(make_world):
    world = make_world(library_json={"route": "both"})
    forced = world.aw_json("library", "read", "--source", "beta", "--pages", "2", env={"AW_LIBRARY_ROUTE": "pageindex"})
    assert forced["route"] == "pageindex" and forced["shadow_status"] == "none"
    assert forced["pages"][0]["text"] == page_text("beta", 2)
    assert world.aw_json("library", "status", env={"AW_LIBRARY_ROUTE": "trove"})["forced"] == "trove"
    row = only(world.rows(), "lookup")[0]
    assert row["mode"] == "pageindex" and row["route_primary"] == "pageindex"
    assert not only(world.rows(), "shadow")
    bad = world.aw("library", "status", env={"AW_LIBRARY_ROUTE": "pageindx"})
    assert bad.returncode == 3 and "AW_LIBRARY_ROUTE must be trove or pageindex" in bad.stderr


def test_without_library_json_trove_is_the_answer_and_the_helper_is_never_started(make_world):
    world = make_world(library_json=None)
    # A tripwire in place of the helper's Python: if anything starts it, the marker appears.
    tripwire = world.root / "pageindex-was-started"
    world._script(world.home / "venv" / "bin" / "python", f"#!/bin/sh\ntouch '{tripwire}'\nexit 1\n")
    status = world.aw_json("library", "status")
    assert (status["route"], status["configured"]) == ("trove", False)
    listed = world.aw_json("library", "list")
    assert sorted(b["id"] for b in listed["items"]) == ["alpha", "beta", "gamma"]
    read = world.aw_json("library", "read", "--source", "alpha", "--pages", "3")
    assert read["route"] == "trove" and read["shadow_status"] == "none" and read["pages"][0]["text"] == page_text("alpha", 3)
    assert not only(world.rows(), "shadow") and [r["mode"] for r in world.rows()] == ["trove", "trove"]
    assert not tripwire.exists(), "with no library.json the helper is never started"
    assert not (world.helper / "library.json").exists(), "reading must not create a route choice"


# ---------------------------------------------------------------------------------------------------------
# (2) aw library index --trove-id: a new item, then the same item changed in Trove (re-index), with read-back


def tree_titles(structure: list) -> list[str]:
    out = []
    for node in structure:
        out.append(node["title"])
        out += tree_titles(node.get("nodes", []))
    return out


def current_version(world_library: pathlib.Path, book: str) -> pathlib.Path:
    name = (world_library / "books" / book / "CURRENT").read_text(encoding="utf-8").strip()
    return world_library / "books" / book / "v" / name


def test_index_new_item_writes_the_trove_outline_with_summaries_and_passes_read_back(make_world):
    world = make_world(library_json={"route": "trove"}, prebuilt=False)
    assert not (world.library / "books").exists() or not list((world.library / "books").iterdir())

    done = world.aw_json("library", "index", "--trove-id", "alpha")
    assert done["ok"] is True and done["pageindex_source"] == "installed"
    assert (done["source"], done["fallback"], done["summaries"]) == ("trove-toc", False, "gemini")
    assert done["n_pages"] == 8 and done["toc_entries"] == 7 and done["nodes"] == 7
    assert done["nodes_with_summary"] == 7 and done["summaries_generated"] == 7 and done["summaries_reused"] == 0
    assert (done["calls"], done["failures"]) == (7, 0)
    assert (done["prompt_tokens"], done["completion_tokens"]) == (7 * 120, 7 * 30) and done["cost_usd"] == pytest.approx(7 * 0.002)
    assert done["read_back"]["ok"] is True and done["read_back"]["trove_compared"] is True and done["read_back"]["problems"] == []
    assert done["read_back"]["checks"]["pages"] is True and done["read_back"]["checks"]["trove_pages"] is True
    assert done["ledger"] == {"run_id": done["ledger"]["run_id"], "step": "library.index", "recorded": True}

    # The same hinted outline that Trove holds: every title and page range, with a summary on each node.
    version = current_version(world.library, "alpha")
    tree = json.loads((version / "tree.json").read_text(encoding="utf-8"))
    assert tree_titles(tree["structure"]) == [t for t, _, _ in TOCS["alpha"]]
    nodes = []
    stack = list(tree["structure"])
    while stack:
        node = stack.pop(0)
        nodes.append(node)
        stack = node.get("nodes", []) + stack
    assert all((n.get("summary") or n.get("prefix_summary", "")).startswith("Summary ") for n in nodes)
    pages = json.loads((version / "pages.json").read_text(encoding="utf-8"))
    assert pages == [page_text("alpha", n) for n in range(1, 9)]
    meta = json.loads((version / "meta.json").read_text(encoding="utf-8"))
    assert meta["origin"]["trove"]["trove_pages"] == 8 and meta["origin"]["trove"]["toc_entries"] == 7

    # The usage ledger got one row for the run, with tokens, cost and time; Trove was only ever read.
    usage = world.usage_of(done["ledger"]["run_id"])
    assert len([r for r in world.usage_rows() if r["step"] == "library.index"]) == 1
    assert usage["exit"] == "OK" and usage["provider"] == "gemini"
    assert (usage["input_tokens"], usage["output_tokens"]) == (840, 210) and usage["cost_usd"] == pytest.approx(0.014)
    assert usage["latency_ms"] >= 0
    assert world.trove_calls() and all(c.split()[1] in ("items", "shelf") and c.split()[2] in ("list", "toc", "read", "current") for c in world.trove_calls())

    # The key reached the stub only through the helper's own environment, never an argument, an output or a file.
    calls = world.litellm_calls()
    assert len(calls) == 7 and {c["key"] for c in calls} == {"plugin"} and not any(c["key_in_argv"] for c in calls)
    assert {c["model"] for c in calls} == {"gemini/gemini-3.8-flash"}
    assert_no_secret_anywhere(world, json.dumps(done))

    # The book answers from PageIndex like any other.
    world.set_library_json({"route": "pageindex"})
    assert world.aw_json("library", "read", "--source", "alpha", "--pages", "5")["pages"][0]["text"] == page_text("alpha", 5)


def test_reindex_existing_item_after_trove_changed_reuses_summaries_and_reads_back(make_world):
    world = make_world(library_json={"route": "trove"}, prebuilt=False)
    first = world.aw_json("library", "index", "--trove-id", "alpha")
    assert first["calls"] == 7 and first["nodes"] == 7
    before = current_version(world.library, "alpha").name

    # The reader adds a ninth page and an afterword to the same Trove item.
    longer = book_json("alpha", toc=TOCS["alpha"] + [("Afterword - Later rulings.", 9, 1)], pages=9)
    world.set_book("alpha", longer)

    again = world.aw_json("library", "index", "--trove-id", "alpha")
    assert again["ok"] and again["n_pages"] == 9 and again["nodes"] == 8 and again["toc_entries"] == 8
    assert (again["summaries_reused"], again["summaries_generated"], again["calls"]) == (7, 1, 1)
    assert again["nodes_with_summary"] == 8
    assert again["read_back"]["ok"] is True and again["read_back"]["trove_compared"] is True
    assert current_version(world.library, "alpha").name != before, "the new book is a new version, published by one pointer change"
    assert [e["page"] for e in world.aw_json("library", "toc", "--source", "alpha", env={"AW_LIBRARY_ROUTE": "pageindex"})["toc"]][-1] == 9
    last = world.aw_json("library", "read", "--source", "alpha", "--pages", "9", env={"AW_LIBRARY_ROUTE": "pageindex"})
    assert last["pages"][0]["text"].endswith("later rulings, with an example and a short objection.")
    # Two index runs, two usage rows; the second paid for one call only.
    # Each row is found by the run id its own command printed, so the order of the run folders (a one-second clock) cannot matter.
    assert first["ledger"]["run_id"] != again["ledger"]["run_id"]
    assert len([r for r in world.usage_rows() if r["step"] == "library.index"]) == 2
    assert [(world.usage_of(r)["input_tokens"], world.usage_of(r)["output_tokens"]) for r in (first["ledger"]["run_id"], again["ledger"]["run_id"])] == [(840, 210), (120, 30)]
    assert len(world.litellm_calls()) == 8


def test_index_through_a_wrapper_keeps_the_plugin_key_out_and_uses_the_wrappers_own(wrapper_world):
    world = wrapper_world("trove")
    shutil.rmtree(world.root / "server-library")
    (world.root / "server-library").mkdir()
    done = world.aw_json("library", "index", "--trove-id", "beta")
    assert done["ok"] and done["pageindex_source"] == "library.json" and done["nodes"] == 4 and done["read_back"]["ok"] is True
    calls = world.litellm_calls()
    assert len(calls) == 4 and {c["key"] for c in calls} == {"server"} and not any(c["key_in_argv"] for c in calls)
    assert_no_secret_anywhere(world, json.dumps(done))


INDEX_COMMAND = re.compile(r"\bindex-(trove|md|pdf)\b")


def dump_names(world: World, who: str) -> set[str]:
    return {file.name for file in world.dumps.glob(f"{who}.*")}


def read_dumps(world: World, who: str, exclude: set[str] = frozenset()) -> list[tuple[str, dict[str, str], str]]:
    """What each invocation of `who` ('helper' or 'wrapper') received: its arguments, its environment and the raw text.
    The files are named at random, so `exclude` (names seen before) is how a later batch is told apart, not an order."""
    out = []
    for file in sorted(world.dumps.glob(f"{who}.*")):
        if file.name in exclude:
            continue
        text = file.read_text(encoding="utf-8")
        first, _, rest = text.partition("\n")
        assert first.startswith("ARGS: "), (file.name, text[:200])
        env = dict(line.split("=", 1) for line in rest.splitlines() if "=" in line)
        out.append((first[len("ARGS: "):], env, text))
    return out


@pytest.mark.parametrize("kind", KINDS)
def test_no_key_reaches_a_pageindex_command_except_the_helper_while_it_writes_summaries(kind, make_world, wrapper_world):
    """Reads the environment each invocation really received (it dumps it to its own file), for EVERY invocation: lookups of
    both routes, the quiet second lookup, and indexing. Nothing may hold a key, except that the plugin's own helper gets the
    Gemini key, as GEMINI_API_KEY, while it indexes. Depends on adapter.ts removing keys from the environment of a lookup."""
    world = make_world(library_json={"route": "both"}) if kind == "installed" else wrapper_world("both")
    who = "helper" if kind == "installed" else "wrapper"
    # The shell really holds every secret (else nothing below could fail).
    assert {name: world.env.get(name) for name in PARENT_SECRETS} == PARENT_SECRETS

    # Lookups: the first route answers, then the quiet second lookup runs on the other library; and a PageIndex-only lookup.
    world.aw_json("library", "list", "--run", "k1")
    world.aw_json("library", "toc", "--source", "alpha", "--run", "k1")
    read = world.aw_json("library", "read", "--source", "alpha", "--pages", "2-3", "--run", "k1")
    only_pageindex = world.aw_json("library", "read", "--source", "beta", "--pages", "2", env={"AW_LIBRARY_ROUTE": "pageindex"})
    assert read["pages"] and only_pageindex["pages"]
    for lookup in only(world.rows(), "lookup"):
        if lookup["mode"] == "both":
            world.wait_for(f"the shadow of {lookup['op']}", lambda i=lookup["lookup_id"]: world.shadow_row(i))
    world.wait_for("no leftover processes", lambda: not world.leftovers(), timeout=30)
    lookup_files = dump_names(world, who)
    lookups = read_dumps(world, who)
    assert not any(INDEX_COMMAND.search(args) and "--help" not in args for args, _, _ in lookups)
    assert len(lookups) >= 4, f"a dump for every lookup that reached PageIndex (3 quiet ones and 1 primary), got {[a for a, _, _ in lookups]}"

    # Indexing a new Trove item, through the same command.
    world.set_book("delta", book_json("beta"))
    done = world.aw_json("library", "index", "--trove-id", "delta")
    assert done["ok"] is True and done["pageindex_source"] == ("installed" if kind == "installed" else "library.json")
    indexing = read_dumps(world, who, exclude=lookup_files)     # what `aw library index` started: its probes and the indexing run itself
    everything = lookups + indexing
    real_indexing = [d for d in indexing if INDEX_COMMAND.search(d[0]) and "--help" not in d[0]]
    assert real_indexing, f"the indexing invocation dumped its environment: {[a for a, _, _ in indexing]}"

    # Every dump is a real environment (not an empty file), and the checks below read the whole text of each.
    for args, env, text in everything:
        assert env.get("AW_E2E_TAG") == str(world.root) and "PATH" in env, (args, list(env)[:5])
    secret_names = list(PARENT_SECRETS)
    # Everything is collected first and judged at the end, so one failure does not hide another.
    problems = []
    for args, env, text in lookups:
        held = [n for n in secret_names if n in env] + [f"value of {k[:16]}" for k in ALL_KEYS if k in text]
        if held:
            problems.append(f"lookup {args[-50:]!r} received {held}")
    for args, env, text in indexing:
        # Only the summary-writing call of the built-in helper (a real `index-*` run) may hold the plugin's key, as GEMINI_API_KEY.
        # Probes (`--help`) and the read-back lookups made while indexing get no key at all.
        writes_summaries = kind == "installed" and INDEX_COMMAND.search(args) is not None and "--help" not in args
        kind_of_call = ("summary-writing indexing" if writes_summaries else "indexing probe" if "--help" in args
                        else "indexing (supplied command)" if INDEX_COMMAND.search(args) else "read-back")
        allowed = {"GEMINI_API_KEY"} if writes_summaries else set()
        held = [n for n in PARENT_SECRETS if n in env and n not in allowed]
        held += [f"value of {k[:16]}" for k in ALL_KEYS if k in text and not (writes_summaries and k == PLUGIN_KEY)]
        if writes_summaries and env.get("GEMINI_API_KEY") != PLUGIN_KEY:
            held.append("no plugin key (the summary-writing call must get the plugin's key as GEMINI_API_KEY)")
        if held:
            problems.append(f"{kind_of_call} {args[-50:]!r} received {held}")
    assert_no_secret_anywhere(world, json.dumps(done), json.dumps(read))
    assert not problems, "keys reached commands (adapter.ts and install.ts childEnv must strip them; only the built-in helper while indexing gets GEMINI_API_KEY): " + "; ".join(problems)


def test_a_book_without_a_hinted_outline_is_refused_in_plain_words_when_the_structure_helper_is_missing(make_world):
    world = make_world(library_json={"route": "trove"}, prebuilt=False, books=("alpha",))
    world.set_book("flat", book_json("flat", toc=FLAT_TOC, pages=4))
    done = world.aw("library", "index", "--trove-id", "flat")
    out = json.loads(done.stdout.strip().splitlines()[-1])
    assert done.returncode == 4 and out["ok"] is False and out["code"] == "structure_helper_missing"
    assert "no table of contents with hints" in out["error"] and "Install the full helper" in out["error"]
    left = sorted(f.name for f in (world.library / "books" / "flat").iterdir()) if (world.library / "books" / "flat").exists() else []
    assert left in ([], [".index.lock"]), f"nothing was published for the book that could not be indexed: {left}"
    assert world.aw_json("library", "list", env={"AW_LIBRARY_ROUTE": "pageindex"})["items"] == []
    dry = world.aw("library", "index", "--trove-id", "flat", "--no-fallback")
    assert dry.returncode == 4 and json.loads(dry.stdout.strip().splitlines()[-1])["code"] == "no_hinted_toc"
    assert not world.litellm_calls()


# ---------------------------------------------------------------------------------------------------------
# (3) backfill of two books


def test_backfill_copies_two_trove_books_and_a_second_run_skips_them(make_world):
    world = make_world(library_json={"route": "pageindex"}, prebuilt=False, books=("beta", "gamma"))
    plan = world.aw_json("library", "backfill", "--ids", "beta,gamma", "--dry-run")
    assert plan["dry_run"] is True and plan["to_index"] == 2 and plan["estimated_calls"] == 4 + 5 and plan["ask_required"] is False
    assert not (world.library / "books").exists() or not list((world.library / "books").iterdir())
    assert not world.litellm_calls()

    done = world.aw_json("library", "backfill", "--ids", "beta,gamma")
    assert done["ok"] and (done["indexed"], done["failed"], done["skipped"]) == (2, 0, 0)
    assert done["calls"] == 9 and done["prompt_tokens"] == 9 * 120 and done["cost_usd"] == pytest.approx(9 * 0.002)
    assert [(r["id"], r["status"], r["nodes"], r["read_back_ok"]) for r in done["results"]] == [("beta", "indexed", 4, True), ("gamma", "indexed", 5, True)]

    # Read back through the route the articles will use: the catalog lists both, and each page is Trove's page.
    assert sorted(b["id"] for b in world.aw_json("library", "list")["items"]) == ["beta", "gamma"]
    assert world.aw_json("library", "read", "--source", "gamma", "--pages", "7")["pages"][0]["text"] == page_text("gamma", 7)
    for book in ("beta", "gamma"):
        meta = json.loads((current_version(world.library, book) / "meta.json").read_text(encoding="utf-8"))
        assert meta["origin"]["trove"]["trove_pages"] == len(TOPICS[book])

    again = world.aw_json("library", "backfill", "--ids", "beta,gamma", "--skip-existing")
    assert (again["indexed"], again["skipped"], again["calls"]) == (0, 2, 0)
    assert len(world.litellm_calls()) == 9
    usage = [r for r in world.usage_rows() if r["step"] == "library.index"]
    assert len(usage) == 2 and sum(r["input_tokens"] for r in usage) == 9 * 120
    assert all(c.split()[1] in ("items", "shelf") for c in world.trove_calls())


# ---------------------------------------------------------------------------------------------------------
# (4) the report: tokens (estimates), latency, cost, auditor PASS rate, agreement, shadow supports


def quote_of(book: str, number: int) -> str:
    return f"This page deals with {TOPICS[book][number - 1]}, with an example"


def test_report_shows_tokens_latency_cost_pass_rate_agreement_and_shadow_supports(make_world):
    world = make_world(library_json={"route": "both"}, prebuilt=False)
    run = "article-1"
    # Cost: one indexing run through the plugin, recorded in the same project's usage ledger.
    indexed = world.aw_json("library", "index", "--trove-id", "gamma", "--run", run)
    assert indexed["calls"] == 5

    # Three auditor checks: the cited page supports two paragraphs; the third cites a page that does not carry the claim.
    checks = [("P1", "gamma", 4, quote_of("gamma", 4), "PASS", None),
              ("P2", "gamma", 5, quote_of("gamma", 5), "PASS", None),
              ("P3", "gamma", 2, quote_of("gamma", 6), "FAIL", "6")]
    for paragraph, book, number, quote, verdict, corrected in checks:
        read = world.aw_json("library", "read", "--source", book, "--pages", str(number), "--run", run, "--claim", paragraph)
        world.wait_for(f"the shadow of {paragraph}", lambda i=read["lookup_id"]: world.shadow_row(i))
        args = ["library", "verdict", "--lookup", read["lookup_id"], "--verdict", verdict, "--support-quote", quote, "--paragraph", paragraph, "--run", run]
        verdict_out = world.aw_json(*args, *(["--corrected-page", corrected] if corrected else []))
        assert verdict_out["verdict"] == verdict
        assert verdict_out["shadow_supports"] is (verdict == "PASS")
    world.assert_rows_valid()

    report = world.aw_json("library", "report", "--run", run, "--json")
    assert report["rows"] == {"lookup": 3, "shadow": 3, "verdict": 3, "invalid": 0}
    assert report["modes"] == {"both, trove answers": 3}
    trove, pageindex = report["routes"]["trove"], report["routes"]["pageindex"]

    # Auditor PASS rate: two of three passed; the quote of the failing paragraph is not on the page the article cited.
    assert (trove["auditor"]["pass"], trove["auditor"]["fail"], trove["auditor"]["fail_with_corrected_page"]) == (2, 1, 1)
    assert trove["auditor"]["pass_rate"] == pytest.approx(2 / 3, abs=1e-3)
    # Shadow-supports: the other library's page supported the claim for the two passes and not for the failure.
    assert (trove["auditor"]["shadow_checked"], trove["auditor"]["shadow_supports"]) == (3, 2)
    assert trove["auditor"]["shadow_supports_rate"] == pytest.approx(2 / 3, abs=1e-3)
    assert report["auditor"]["shadow_supports_by_verdict"]["PASS"] == {"supports": 2, "not_supports": 0, "unknown": 0}
    assert report["auditor"]["shadow_supports_by_verdict"]["FAIL"] == {"supports": 0, "not_supports": 1, "unknown": 0}
    assert report["auditor"]["lookups_with_verdict"] == report["auditor"]["read_lookups"] == 3
    # Agreement: both libraries returned the same text for every page.
    assert trove["agreement"] == {"pages_compared": 3, "pages_agreed": 3, "rate": 1}
    assert report["agreement"] == {"lookups_compared": 3, "pages_compared": 3, "pages_agreed": 3, "rate": 1}
    assert (pageindex["shadow_runs"], pageindex["shadow_errors"], pageindex["shadow_timeouts"]) == (3, 0, 0)

    # Latency, per route: the answering route's lookups and the other route's quiet runs.
    assert trove["lookups"] == 3 and 0 <= trove["latency_ms"]["p50"] <= trove["latency_ms"]["p90"]
    assert pageindex["shadow_latency_ms"]["p50"] > 0 and trove["by_op"]["read"]["lookups"] == 3

    # Tokens are labelled as estimates. Both libraries returned the same pages, so the same figure; it matches the page
    # text within the rounding of three lookups (an independent count: four characters to the token).
    tokens = report["tokens"]
    assert tokens["basis"] == "estimate" and tokens["other_chars_per_token"] == 4
    chars = sum(len(page_text("gamma", n)) for n in (4, 5, 2))
    assert abs(tokens["routes"]["trove"]["total"] - chars / 4) <= 3
    assert tokens["routes"]["trove"]["lookups_measured"] == 3 and tokens["routes"]["trove"]["pages_measured"] == 3
    assert tokens["routes"]["pageindex"]["shadow"]["runs_measured"] == 3
    assert tokens["routes"]["pageindex"]["shadow"]["total"] == tokens["routes"]["trove"]["total"]
    assert tokens["routes"]["trove"]["per_page_avg"] == pytest.approx(tokens["routes"]["trove"]["total"] / 3, abs=1)
    assert report["agents"]["runs"] == 0

    # Cost and time of building the second library: the indexing run, with its tokens (five summaries from the stub).
    indexing = report["indexing"]
    assert (indexing["runs"], indexing["failed"]) == (1, 0)
    assert (indexing["input_tokens"], indexing["output_tokens"]) == (5 * 120, 5 * 30)
    assert indexing["cost_usd"]["total"] == pytest.approx(5 * 0.002) and indexing["cost_usd"]["known_runs"] == 1
    assert indexing["wall_ms"]["p50"] > 0 and indexing["models"] == ["gemini/gemini-3.8-flash"]

    text = world.aw("library", "report", "--run", run).stdout
    assert "Auditor: 2 of 3 citations passed (66.7%)" in text
    assert "also supported the claim for 2 of 3 checked (66.7%)" in text
    assert "the other library returned the same page text for 3 of 3 pages (100%)" in text
    assert "Ran quietly alongside 3 times: 0 failed, 0 timed out" in text
    assert "token figures are estimates" in text and f"about {tokens['routes']['trove']['total']} tokens in all" in text
    assert "Indexing (page summaries for PageIndex" in text and "600 tokens in and 150 out, cost $0.010" in text
    world.wait_for("no leftover processes", lambda: not world.leftovers(), timeout=30)
    assert_no_secret_anywhere(world, text, json.dumps(report))


# ---------------------------------------------------------------------------------------------------------
# (5) a full blind evaluation round, with a fake `claude` playing the locating agent

CLAIM_PAGES = {"alpha": [3, 5, 6, 7], "beta": [2, 3, 5, 6], "gamma": [2, 4, 5, 6]}
UNITS = {"alpha": "U1", "beta": "U2", "gamma": "U3"}
# What the scripted agents answer, by the claim's position in the plan (position mod 5):
#   0 both libraries name the right page (identical answers: the pair is "same" by code)
#   1 only Trove names the right page            2 only PageIndex names it
#   3 only PageIndex names it (as its second page) 4 neither does (two different wrong pages)
USAGE = {"trove": {"input": 1500, "output": 200, "cost_usd": 0.021, "duration_ms": 4000},
         "pageindex": {"input": 900, "output": 150, "cost_usd": 0.012, "duration_ms": 2500}}


def claim_sentence(book: str, page: int) -> str:
    return f"The {TITLES[book]} sets out {TOPICS[book][page - 1]} on a page of its own argument."


def write_article(world: World) -> None:
    """Twelve cited sentences in three draft units, and the registry that says which source and page each footnote means."""
    drafts = world.helper / "drafts"
    drafts.mkdir(exist_ok=True)
    passages = []
    for book, unit in UNITS.items():
        paragraphs = []
        for page in CLAIM_PAGES[book]:
            paragraphs.append(f"{claim_sentence(book, page)}[^{book}-{page}]")
            passages.append({"id": f"{book}-{page}", "sourceId": book, "locator": f"Page {page} (orig. {page - 1})"})
        (drafts / f"{unit}.md").write_text("\n\n".join(paragraphs) + "\n", encoding="utf-8")
    (world.helper / "sources.json").write_text(json.dumps([{"sourceId": b, "workTitle": TITLES[b]} for b in UNITS]), encoding="utf-8")
    (world.helper / "evidence.json").write_text(json.dumps({"passages": passages}), encoding="utf-8")


def wrong_page(book: str, right: int, shift: int) -> int:
    count = len(TOPICS[book])
    page = (right + shift) % count + 1
    return page if page != right else page % count + 1


def agent_script(world: World, plan: dict) -> dict:
    answers = {}
    for index, claim in enumerate(plan["claims"]):
        book, right = claim["source_id"], claim["cited_trove_pages"][0]
        kind = index % 5
        answers[claim["text"]] = {
            0: {"trove": [right], "pageindex": [right]},
            1: {"trove": [right], "pageindex": [wrong_page(book, right, 1)]},
            2: {"trove": [wrong_page(book, right, 2)], "pageindex": [right]},
            3: {"trove": [wrong_page(book, right, 1)], "pageindex": [wrong_page(book, right, 2), right]},
            4: {"trove": [wrong_page(book, right, 1)], "pageindex": [wrong_page(book, right, 3)]},
        }[kind]
        answers[claim["text"]] = {route: {"book": book, "pages": pages} for route, pages in answers[claim["text"]].items()}
    path = world.root / "agent-script.json"
    path.write_text(json.dumps({"answers": answers, "usage": USAGE}), encoding="utf-8")
    return {"FAKE_CLAUDE_SCRIPT": str(path), "AW_EVAL_CLAUDE_COMMAND": str(world._script(world.bin / "claude", fill(FAKE_CLAUDE, PYTHON=sys.executable)))}


def wilson95(successes: int, n: int) -> tuple[float, float]:
    z = 1.959963984540054
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def sign_test_p(wins: int, n: int) -> float:
    low = min(wins, n - wins)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(low + 1)) / 2 ** n)


def record_auditor_passes(world: World, plan_less_claims: list[tuple[str, int, str]]) -> None:
    """Before the evaluation, the citation checker has already passed some paragraphs of the draft (through aw, like a real run)."""
    for paragraph, page, book in plan_less_claims:
        read = world.aw_json("library", "read", "--source", book, "--pages", str(page), "--run", "draft-run", "--claim", paragraph)
        world.aw_json("library", "verdict", "--lookup", read["lookup_id"], "--verdict", "PASS", "--paragraph", paragraph, "--run", "draft-run",
                      "--support-quote", quote_of(book, page))


def test_full_blind_evaluation_round_with_a_fake_agent_ends_in_exact_win_rates(make_world):
    world = make_world(library_json={"route": "trove"})  # Trove stays the default; the evaluation forces each route itself
    write_article(world)
    # The checker passed the first cited paragraph of each unit.
    record_auditor_passes(world, [(f"{unit}_p_1", CLAIM_PAGES[book][0], book) for book, unit in UNITS.items()])

    planned = world.aw_json("library", "eval", "plan", "--eval", "ev-e2e", "--n", "10", "--seed", "plan-seed")
    assert planned["eval_id"] == "ev-e2e" and planned["claims"] == 10 and planned["runs"] == 20 and planned["skipped"]["unresolved"] == 0
    plan = json.loads((world.helper / "library-eval" / "ev-e2e" / "plan.json").read_text(encoding="utf-8"))
    assert sorted({c["source_id"] for c in plan["claims"]}) == ["alpha", "beta", "gamma"]
    assert all(c["cited_trove_pages"] and c["text"] == claim_sentence(c["source_id"], c["cited_trove_pages"][0]) for c in plan["claims"])
    passed = [c for c in plan["claims"] if c["auditor_verdict"] == "PASS"]
    assert passed and all(c["paragraph_id"].endswith("_p_1") for c in passed)

    fake = agent_script(world, plan)
    ran = world.aw_json("library", "eval", "run", "--eval", "ev-e2e", "--parallel", "4", "--timeout-s", "300", env=fake)
    assert (ran["planned"], ran["done"], ran["failed"], ran["invalid"], ran["skipped"]) == (20, 20, 0, 0, 0)
    assert ran["cost_usd"] == pytest.approx(10 * (0.021 + 0.012))
    assert world.leftovers() == [], "every agent and everything it started is gone when the run returns"
    status = world.aw_json("library", "eval", "status", "--eval", "ev-e2e")
    assert status["stage"] == "located" and status["runs"] == {"expected": 20, "finished": 20, "failed": 0}

    # Pairs, the judging page: nothing in what the judge sees names a library.
    built = world.aw_json("library", "eval", "pairs", "--eval", "ev-e2e", "--seed", "pair-seed")
    assert built["pairs"] == 10 and built["auto_same"] == 2 and built["excluded"] == []
    page = world.aw_json("library", "eval", "page", "--eval", "ev-e2e", env={"CLAUDE_PLUGIN_ROOT": str(world.plugin)})
    folder = world.helper / "library-eval" / "ev-e2e"
    pairs_text = (folder / "pairs.json").read_text(encoding="utf-8")
    html = pathlib.Path(page["out"]).read_text(encoding="utf-8")
    assert page["pairs"] == 10 and pathlib.Path(page["out"]) == folder / "judge.html"
    assert not ROUTE_WORDS.search(pairs_text) and not ROUTE_WORDS.search(html), "a library name is visible to the judge"
    pairs = json.loads(pairs_text)
    assert set(pairs) == {"schema", "eval_id", "created_at", "mapping_sha256", "pairs"}
    assert all(set(p) == {"pair_id", "claim", "auto_same", "options"} and set(p["options"]) == {"A", "B"} for p in pairs["pairs"])
    assert all(set(o) == {"book", "book_title", "pages"} for p in pairs["pairs"] for o in p["options"].values())
    assert pairs["pairs"][0]["claim"]["text"] in html and re.search(r'id="pairs"', html)
    mapping_file = folder / "sealed" / "mapping.json"
    assert mapping_file.exists() and (mapping_file.stat().st_mode & 0o077) == 0, "the key is sealed (owner only)"
    assert hashlib.sha256(mapping_file.read_bytes()).hexdigest() not in html
    for text in (json.dumps(status), json.dumps(built), json.dumps(page), world.aw("library", "eval", "status", "--eval", "ev-e2e").stdout):
        assert not ROUTE_WORDS.search(text)

    # Nobody can open the key before judging.
    early = world.aw("library", "eval", "unblind", "--eval", "ev-e2e")
    assert early.returncode == 2 and "no judgments are imported yet" in early.stderr and "Win rate" not in early.stdout

    # The judge: reads only pairs.json, picks the option whose pages include the page the claim is about.
    truth = {c["id"]: c["cited_trove_pages"][0] for c in plan["claims"]}
    verdicts = []
    for pair in pairs["pairs"]:
        right = truth[pair["claim"]["id"]]
        has = {side: right in [p["page"] for p in option["pages"]] for side, option in pair["options"].items()}
        if pair["auto_same"]:
            continue
        verdict = "A" if has["A"] and not has["B"] else "B" if has["B"] and not has["A"] else "neither"
        verdicts.append({"pair_id": pair["pair_id"], "verdict": verdict, "note": "neither page is about the claim" if verdict == "neither" else "", "at": "2026-10-16T10:00:00Z"})
    assert len(verdicts) == 8
    judged_file = world.root / "judgments.json"
    judged_file.write_text(json.dumps({"schema": 1, "eval_id": "ev-e2e", "judgments": verdicts}), encoding="utf-8")
    imported = world.aw_json("library", "eval", "import", "--eval", "ev-e2e", "--file", str(judged_file))
    assert (imported["imported"], imported["auto_same"], imported["judged"], imported["pairs"], imported["pending"]) == (8, 2, 10, 10, [])
    assert world.aw_json("library", "eval", "status", "--eval", "ev-e2e")["stage"] == "judged"

    # Unblind: the win rates, exact, from the scripted answers (positions 1 -> Trove, 2 and 3 -> PageIndex, 4 -> neither, 0 -> same).
    positions = range(10)
    trove_wins = sum(1 for i in positions if i % 5 == 1)
    pageindex_wins = sum(1 for i in positions if i % 5 in (2, 3))
    neither = sum(1 for i in positions if i % 5 == 4)
    assert (trove_wins, pageindex_wins, neither) == (2, 4, 2)
    report = world.aw_json("library", "eval", "unblind", "--eval", "ev-e2e", "--json")
    t, p = report["routes"]["trove"], report["routes"]["pageindex"]
    assert (t["wins"], t["losses"], t["ties"], t["neither"]) == (2, 4, 2, 2)
    assert (p["wins"], p["losses"], p["ties"], p["neither"]) == (4, 2, 2, 2)
    assert report["decisive"] == 6 and report["n_pairs"] == 10 and report["n_judged"] == 8 and report["n_auto_same"] == 2 and report["enough_pairs"] is True
    assert t["win_rate"] == pytest.approx(2 / 6) and p["win_rate"] == pytest.approx(4 / 6)
    assert p["win_rate_ci95"] == pytest.approx(list(wilson95(4, 6)))
    assert report["sign_test"]["p_value"] == pytest.approx(sign_test_p(4, 6)) and sign_test_p(4, 6) == pytest.approx(0.6875)
    assert "PageIndex won 4 of the 6 pairs with a clear winner, a win rate of 67%" in report["statement"]
    # The cited page: which library found the page the article cites (positions 0 and 1 for Trove; 0, 2 and 3 for PageIndex).
    assert (t["cited_page_hit"]["hits"], t["cited_page_hit"]["eligible"]) == (4, 10)
    assert (p["cited_page_hit"]["hits"], p["cited_page_hit"]["eligible"]) == (6, 10)
    # Agents: exact tokens and cost of the scripted runs, per library.
    assert (t["tokens"]["input_total"], t["tokens"]["output_total"], t["cost_usd"]["total"]) == (15000, 2000, pytest.approx(0.21))
    assert (p["tokens"]["input_total"], p["tokens"]["output_total"], p["cost_usd"]["total"]) == (9000, 1500, pytest.approx(0.12))
    assert t["tool_calls_median"] == p["tool_calls_median"] == 2 and t["returned_est_tokens"]["total"] > 0
    # Agreement with the citation checker: among pairs with a clear winner on a PASSed claim, the judge preferred the library that found the cited page.
    decisive_passed = [row for row in report["pairs"] if row["preferred"] and next(c for c in plan["claims"] if c["id"] == row["claim_id"])["auditor_verdict"] == "PASS"]
    assert report["auditor_agreement"]["eligible"] == len(decisive_passed) > 0
    assert report["auditor_agreement"]["agree"] == len(decisive_passed) and report["auditor_agreement"]["disagree"] == 0
    # Every pair names its sides only now; the note the judge wrote is kept.
    assert {r["option_routes"]["A"] for r in report["pairs"]} == {"trove", "pageindex"}
    assert sum(1 for r in report["pairs"] if r["note"] == "neither page is about the claim") == 2
    text = world.aw("library", "eval", "unblind", "--eval", "ev-e2e").stdout
    assert "# Which library found the right pages? (ev-e2e)" in text and "PageIndex won 4 of the 6 pairs" in text
    assert (folder / "report.md").exists() and (folder / "report.json").exists()

    # The same agents show up in the library report with their tokens and cost, never mixed with the judging fetches.
    agents = world.aw_json("library", "report", "--eval", "ev-e2e", "--json")["agents"]
    assert agents["runs"] == 20 and agents["unattributed"] == 0
    for route, usage in USAGE.items():
        row = agents["routes"][route]
        assert (row["runs"], row["failed"], row["retried"]) == (10, 0, 0)
        assert (row["input_tokens"]["total"], row["output_tokens"]["total"]) == (10 * usage["input"], 10 * usage["output"])
        assert row["cost_usd"]["total"] == pytest.approx(10 * usage["cost_usd"]) and row["cost_usd"]["known_runs"] == 10
        assert row["lookups_per_run"]["total"] == 20 and row["returned_est_tokens_per_run"]["total"] > 0
    world.assert_rows_valid()
    assert_no_secret_anywhere(world, text, json.dumps(report))
    assert world.leftovers() == []


def test_an_agent_that_leaves_a_blocking_child_behind_is_cleaned_up_by_the_run(make_world):
    """A locating agent starts a process in a session of its own that never ends. The run stops it before it returns
    (found by the run tag in its environment, or by following the agent's process tree), so nothing outlives the run."""
    world = make_world(library_json={"route": "trove"})
    claims = [{"text": claim_sentence("beta", 2), "source": "beta", "trove_pages": [2]}]
    (world.root / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
    world.aw_json("library", "eval", "plan", "--eval", "ev-linger", "--claims", str(world.root / "claims.json"), "--n", "1")
    plan = json.loads((world.helper / "library-eval" / "ev-linger" / "plan.json").read_text(encoding="utf-8"))
    assert len(plan["claims"]) == 1
    fake = agent_script(world, plan)
    fake.update(FAKE_CLAUDE_LINGER=str(world.root / "blocker"), FAKE_CLAUDE_LINGER_PID=str(world.root / "blocker.pid"))

    ran = world.aw_json("library", "eval", "run", "--eval", "ev-linger", "--parallel", "2", "--timeout-s", "300", env=fake)
    assert (ran["done"], ran["failed"], ran["invalid"]) == (2, 0, 0)
    started = sorted(world.root.glob("blocker.pid.*"))
    assert len(started) == 2, "every agent really started its blocking child"
    blockers = [int(f.read_text()) for f in started]
    for pid in blockers:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    assert world.leftovers() == []


def test_an_interrupted_evaluation_run_stops_its_agents_and_exits_with_the_signal(make_world):
    """Ctrl-C (SIGINT) during `eval run`: the agent's own blocker is stopped and aw exits with 128 + the signal number."""
    world = make_world(library_json={"route": "trove"})
    claims = [{"text": claim_sentence("beta", 2), "source": "beta", "trove_pages": [2]}]
    (world.root / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
    world.aw_json("library", "eval", "plan", "--eval", "ev-int", "--claims", str(world.root / "claims.json"), "--n", "1")
    plan = json.loads((world.helper / "library-eval" / "ev-int" / "plan.json").read_text(encoding="utf-8"))
    fake = agent_script(world, plan)
    # An agent that never answers: it records that it started, then becomes a blocked process (exec keeps the pid).
    hang = world.bin / "claude-hang"
    world._script(hang, fill('#!@@PYTHON@@\nimport os, sys\nsys.stdin.read()\nopen("@@MARK@@", "w").write(str(os.getpid()))\n'
                             'os.execv(sys.executable, [sys.executable, "-c", "import time; time.sleep(600)", "@@TAG@@"])\n',
                             PYTHON=sys.executable, MARK=str(world.root / "hang.started"), TAG=str(world.root)))
    env = {**world.env, **fake, "AW_EVAL_CLAUDE_COMMAND": str(hang)}
    run = subprocess.Popen([str(world.aw_path), "--data-dir", str(world.data), "--project-dir", str(world.project), "library", "eval", "run",
                            "--eval", "ev-int", "--parallel", "1", "--timeout-s", "600"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                           cwd=str(world.project))
    try:
        marker = world.root / "hang.started"
        world.wait_for("the agent to start", lambda: marker.exists() and marker.read_text().strip())
        agent_pid = int(marker.read_text())
        run.send_signal(signal.SIGINT)
        out, err = run.communicate(timeout=60)
    finally:
        if run.poll() is None:
            run.kill()
    assert run.returncode == 128 + signal.SIGINT, (run.returncode, out[-300:], err[-300:])
    with pytest.raises(ProcessLookupError):
        os.kill(agent_pid, 0)
    assert world.leftovers() == []
