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
_SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)", re.IGNORECASE)
_MODEL_PREFIX = ("GEMINI_", "GOOGLE_", "OPENAI_", "ANTHROPIC_", "OPENROUTER_")
_TROVE_OWN = ("TROVE_", "CANDLEKEEP_", "CK_")  # how Trove itself logs in


def trove_env(env=None) -> dict:
    """The environment for a `trove` child: everything except model keys and other secrets (Trove's own variables stay)."""
    out = {}
    for name, value in (os.environ if env is None else env).items():
        upper = name.upper()
        if upper.startswith(_TROVE_OWN):
            out[name] = value
        elif upper.startswith(_MODEL_PREFIX) or _SECRET_NAME.search(name):
            continue
        else:
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
    pages_doc = _json(trove("items", "read", f"{trove_id}:all", "--json"), f"trove items read {trove_id}:all")
    got = first_item(pages_doc, f"trove items read {trove_id}:all")
    if pages_doc.get("truncatedItemIds") or got.get("truncated"):
        raise IndexFailure("trove_truncated", f"Trove truncated the full read of {trove_id}; it is too large to index in one read")
    pages = {}
    for entry in got.get("pages") or []:
        try:
            number = int(entry["pageNum"])
        except (KeyError, TypeError, ValueError):
            continue
        pages[number] = entry.get("content") or ""
    return {"title": item.get("title") or got.get("title") or trove_id,
            "author": item.get("author") or got.get("author") or "",
            "toc": toc, "pages": pages}
