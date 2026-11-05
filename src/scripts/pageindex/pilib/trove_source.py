"""Read one book from Trove (read-only): its table of contents and every page, exactly as stored.

Everything here shells out to the `trove` command that is already logged in on this machine. Page numbers
are Trove page numbers (1..N), which is the canonical page space of the whole plugin.
"""
from __future__ import annotations

import json
import os
import re
import subprocess

from .errors import IndexFailure, scrub

# pilib holds a model key (for LiteLLM); the `trove` command it starts is another program and must not see it.
# An allow-list that matches `allowedEnv(env, 'trove')` in src/cli/src/library/backends.ts: keep the two in step.
_BASE_NAMES = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "LANG", "LANGUAGE", "TMPDIR", "TEMP", "TMP", "TERM", "SHELL", "TZ", "SSH_AUTH_SOCK",
    "SYSTEMROOT", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
})
_BASE_PREFIXES = ("LC_", "XDG_")
_TROVE_OWN = ("TROVE_", "CANDLEKEEP_", "CK_")  # how Trove itself logs in
_SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH)", re.IGNORECASE)
_VALID_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PASS_ENV = "AW_LIBRARY_PASS_ENV"  # names the researcher opts in, comma separated


def trove_env(env=None) -> dict:
    """The environment for a `trove` child: an allow-list (base names, Trove's own variables, non-secret AW_*, names in AW_LIBRARY_PASS_ENV)."""
    source = os.environ if env is None else env
    listed = {n.strip() for n in source.get(PASS_ENV, "").split(",") if _VALID_NAME.match(n.strip())}
    out = {}
    for name, value in source.items():
        if (
            name in _BASE_NAMES
            or name.startswith(_BASE_PREFIXES)
            or (name.startswith("AW_") and not _SECRET_NAME.search(name))
            or name.startswith(_TROVE_OWN)
            or name in listed
        ):
            out[name] = value
    return out


def trove(*args: str) -> str:
    try:
        out = subprocess.run(["trove", *args, "--no-session"], capture_output=True, text=True, encoding="utf-8", env=trove_env())
    except FileNotFoundError:
        raise IndexFailure("trove_failed", "the trove command was not found on this machine")
    if out.returncode != 0:
        raise IndexFailure("trove_failed", f"trove {' '.join(args)} failed: {scrub(out.stderr)}")
    return out.stdout


def _json(text: str, what: str) -> dict:
    try:
        doc = json.loads(text)
    except ValueError:
        raise IndexFailure("trove_failed", f"{what} did not return JSON")
    if not isinstance(doc, dict):
        raise IndexFailure("trove_failed", f"{what} returned an unexpected shape")
    return doc


def first_item(doc: dict, what: str) -> dict:
    items = doc.get("items")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise IndexFailure("trove_failed", f"{what} returned no item")
    return items[0]


def fetch(trove_id: str) -> dict:
    """{"title", "author", "toc": [raw entries], "pages": {number: text}}; read-only on Trove."""
    toc_doc = _json(trove("items", "toc", trove_id, "--json"), f"trove items toc {trove_id}")
    item = first_item(toc_doc, f"trove items toc {trove_id}")
    toc = item.get("toc") if isinstance(item.get("toc"), list) else []
    pages, got = read_pages(trove_id, "all")
    return {"title": item.get("title") or got.get("title") or trove_id,
            "author": item.get("author") or got.get("author") or "",
            "toc": toc, "pages": pages}


READ_MAX_CALLS = 500


def read_pages(trove_id: str, spec: str = "all") -> tuple[dict, dict]:
    """({page number: full text}, first reply item) for the pages in `spec`, read-only on Trove.

    One `trove items read` reply holds about 20,000 bytes: a longer read comes back with fewer
    pages, `truncated` false, and the rest named only in `next` (`{"pages": "8-23"}`, plus
    `"part": n` when a page over the limit continues). Reading `<id>:all` once indexed 7 of 23
    pages of a real course book (2026-11-05). Follow the cursor to its end and join the parts of
    each page; a repeating cursor, or a reply Trove itself marks truncated, is a failure.
    """
    what = f"trove items read {trove_id}:{spec}"
    pages: dict = {}
    first: dict | None = None
    args = ["items", "read", f"{trove_id}:{spec}", "--json"]
    seen: set = set()
    for _ in range(READ_MAX_CALLS):
        doc = _json(trove(*args), what)
        got = first_item(doc, what)
        if doc.get("truncatedItemIds") or got.get("truncated"):
            raise IndexFailure("trove_truncated", f"Trove truncated the read of {trove_id}; it is too large to index")
        first = first if first is not None else got
        for entry in got.get("pages") or []:
            try:
                number = int(entry["pageNum"])
                part = int(entry.get("part") or 1)
            except (KeyError, TypeError, ValueError):
                continue
            text = entry.get("content") or ""
            pages[number] = pages[number] + text if part > 1 and number in pages else text
        nxt = got.get("next")
        if not isinstance(nxt, dict) or not nxt.get("pages"):
            return pages, first
        key = (str(nxt["pages"]), nxt.get("part"))
        if key in seen:
            raise IndexFailure("trove_failed", f"{what}: the next cursor repeated at {nxt}")
        seen.add(key)
        args = ["items", "read", trove_id, "--pages", str(nxt["pages"])]
        if nxt.get("part"):
            args += ["--part", str(nxt["part"])]
        args.append("--json")
    raise IndexFailure("trove_failed", f"{what}: more than {READ_MAX_CALLS} replies without reaching the end")
