"""Shared helpers for the pilib tests: a fake `trove` on PATH, a stub `litellm`, and an in-process runner.

Nothing here needs PageIndex, litellm, WeasyPrint or the network.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import threading
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PKG = REPO / "src" / "scripts" / "pageindex"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

BOOKS = HERE / "books"


def install_fake_trove(tmp_path, monkeypatch, books=("hinted-demo", "flat-demo")):
    """Copy fixture books into tmp_path and put a `trove` script that serves them first on PATH.
    Returns (data_dir, log_path)."""
    data = Path(tmp_path) / "trove-data"
    for name in books:
        shutil.copytree(BOOKS / name, data / "books" / name)
    bindir = Path(tmp_path) / "bin"
    bindir.mkdir(exist_ok=True)
    script = bindir / "trove"
    script.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{HERE / "fake_trove.py"}" "$@"\n')
    script.chmod(0o755)
    log = Path(tmp_path) / "trove-calls.log"
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_TROVE_DIR", str(data))
    monkeypatch.setenv("FAKE_TROVE_LOG", str(log))
    monkeypatch.delenv("FAKE_TROVE_TRUNCATED", raising=False)
    return data, log


class StubLitellm(types.ModuleType):
    """A stand-in for the litellm module. completion() answers with a summary derived from the prompt, records
    every call, prints a line to stdout (a library may do that), and can be told to fail."""

    def __init__(self):
        super().__init__("litellm")
        self.prompts = []
        self.kwargs = []
        self.models = []
        self.fail_when = None      # callable(prompt) -> bool
        self.fail_text = "service unavailable"
        self.noise = True
        self.suppress_debug_info = False
        self._lock = threading.Lock()

    def completion(self, *args, model=None, messages=None, **kwargs):
        prompt = messages[0]["content"]
        with self._lock:
            self.prompts.append(prompt)
            self.kwargs.append(kwargs)
            self.models.append(model)
        if self.noise:
            print("litellm: a line a library prints")
        if self.fail_when and self.fail_when(prompt):
            raise RuntimeError(self.fail_text)
        text = "SUM:" + hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8]
        usage = types.SimpleNamespace(prompt_tokens=10, completion_tokens=5,
                                      completion_tokens_details=types.SimpleNamespace(reasoning_tokens=2))
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=text))],
                                     usage=usage)

    async def acompletion(self, *args, **kwargs):
        return self.completion(*args, **kwargs)

    def completion_cost(self, completion_response=None):
        return 0.001


def install_litellm(monkeypatch) -> StubLitellm:
    stub = StubLitellm()
    monkeypatch.setitem(sys.modules, "litellm", stub)
    return stub


def run_main(argv, capsys):
    """Run `pilib <argv>` in this process. Returns (exit_code, stdout, stderr)."""
    from pilib.__main__ import main
    capsys.readouterr()
    code = 0
    try:
        main(argv)
    except SystemExit as exit_:
        code = exit_.code if isinstance(exit_.code, int) else 1
        if isinstance(exit_.code, str):
            print(exit_.code, file=sys.stderr)
    out, err = capsys.readouterr()
    return code, out, err


def run_json(argv, capsys):
    """Like run_main but parses stdout as the single JSON object an index command prints."""
    code, out, err = run_main(argv, capsys)
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 1, f"stdout must be exactly one JSON line, got {out!r}"
    return code, json.loads(lines[0]), err


def fixture_json(book, name):
    return json.loads((BOOKS / book / name).read_text(encoding="utf-8"))


def fixture_pages(book):
    return [p["content"] for p in fixture_json(book, "read.json")["items"][0]["pages"]]
