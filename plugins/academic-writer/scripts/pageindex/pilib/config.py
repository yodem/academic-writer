"""Settings pilib needs: the pinned versions and the indexing defaults.

The defaults live in the plugin's thresholds.json (`library.index`), which sits two folders above this
package both in the source tree and in the built plugin. A pilib copied somewhere without that file (a
server that only has this package) falls back to the same values written here; a test keeps them equal.
"""
from __future__ import annotations

import json
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent.parent  # the folder holding pilib/, PINNED.json, requirements
THRESHOLDS = PACKAGE_DIR.parent.parent / "thresholds.json"

INDEX_DEFAULTS = {"summaryModel": "gemini/gemini-3.8-flash", "maxCalls": 3000, "concurrency": 16}


def pinned() -> dict:
    try:
        return json.loads((PACKAGE_DIR / "PINNED.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def pageindex_commit():
    return (pinned().get("pageindex") or {}).get("commit")


def index_settings() -> dict:
    out = dict(INDEX_DEFAULTS)
    try:
        block = json.loads(THRESHOLDS.read_text(encoding="utf-8")).get("library", {}).get("index", {})
    except (OSError, ValueError):
        block = {}
    for key in INDEX_DEFAULTS:
        if key in block:
            out[key] = block[key]
    return out
