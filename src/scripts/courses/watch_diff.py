"""Pure seen-state diff for the Chrome-driven Lemida watcher (T1).

No I/O, no network. Pages are plain dicts (see the plan's PageData model); `seen` is
{"modules": {cmid: {...}}, "discussions": {id: reply_count}, "assigns": {cmid: {...}}, "sections": {id: name}}.
"""
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from typing import Any


class WatchSchemaError(ValueError):
    """A page extracted from Chrome does not match the expected shape."""


@dataclass
class Diff:
    new_modules: list[dict[str, Any]] = field(default_factory=list)
    new_sections: list[dict[str, Any]] = field(default_factory=list)
    new_discussions: list[dict[str, Any]] = field(default_factory=list)
    reply_growth: list[dict[str, Any]] = field(default_factory=list)
    new_assigns: list[dict[str, Any]] = field(default_factory=list)
    changed_assigns: list[dict[str, Any]] = field(default_factory=list)
    last_content_section: str | None = None
    suspect: bool = False

    def is_empty(self) -> bool:
        return not (self.new_modules or self.new_sections or self.new_discussions
                    or self.reply_growth or self.new_assigns or self.changed_assigns)


_REQUIRED = {
    "course": ("sections", "declared_module_count"),
    "forum": ("discussions",),
    "discussion": ("id", "text"),
    "assign": ("cmid", "text", "time_left_text", "due_text"),
}


def _sha(text: Any) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def validate_page(data: dict[str, Any]) -> None:
    """Raise WatchSchemaError unless `data` is a well-formed page of a known kind."""
    if not isinstance(data, dict):
        raise WatchSchemaError("page is not a dict")
    kind = data.get("kind")
    if kind not in _REQUIRED:
        raise WatchSchemaError(f"unknown page kind: {kind!r}")
    if not isinstance(data.get("url"), str) or not data["url"]:
        raise WatchSchemaError("page has no url")
    for key in _REQUIRED[kind]:
        if key not in data:
            raise WatchSchemaError(f"{kind} page missing {key!r}")
    if kind == "course" and not isinstance(data["declared_module_count"], int):
        raise WatchSchemaError("declared_module_count must be an int")


def _empty_seen() -> dict[str, Any]:
    return {"modules": {}, "discussions": {}, "assigns": {}, "sections": {}}


def baseline(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a seen-state that marks everything on `pages` as already seen."""
    seen = _empty_seen()
    for page in pages:
        validate_page(page)
        kind = page["kind"]
        if kind == "course":
            for sec in page["sections"]:
                seen["sections"][str(sec["id"])] = sec["name"]
                for m in sec["modules"]:
                    seen["modules"][str(m["cmid"])] = {"name": m["name"], "type": m["type"], "section": str(sec["id"])}
        elif kind == "forum":
            for d in page["discussions"]:
                seen["discussions"][str(d["id"])] = d["replies"]
        elif kind == "assign":
            seen["assigns"][str(page["cmid"])] = {"due_text": page["due_text"], "text_sha": _sha(page["text"])}
    return seen


def _is_suspect(page: dict[str, Any], seen: dict[str, Any]) -> bool:
    actual = sum(len(sec["modules"]) for sec in page["sections"])
    if actual < page["declared_module_count"]:
        return True
    known = len(seen.get("modules", {}))
    return actual < known


def diff_course(pages: list[dict[str, Any]], seen: dict[str, Any], *, legacy_seen: dict[str, Any] | None = None,
                sources: list[dict[str, Any]] | None = None) -> Diff:
    """Compare freshly extracted pages with `seen`; suspect course pages are ignored."""
    diff = Diff()
    known = set(seen.get("modules", {})) | {str(k) for k in (legacy_seen or {})}
    known |= {str(s["origin_ref"])[3:] for s in (sources or []) if str(s.get("origin_ref", "")).startswith("cm:")}
    for page in pages:
        validate_page(page)
        kind = page["kind"]
        if kind == "course":
            if _is_suspect(page, seen):
                diff.suspect = True
                continue
            for sec in page["sections"]:
                sid = str(sec["id"])
                if sid not in seen.get("sections", {}):
                    diff.new_sections.append({"id": sid, "name": sec["name"]})
                if sec["modules"]:
                    diff.last_content_section = sid
                for m in sec["modules"]:
                    if str(m["cmid"]) not in known:
                        diff.new_modules.append({**m, "section_id": sid, "section_name": sec["name"]})
        elif kind == "forum":
            for d in page["discussions"]:
                did = str(d["id"])
                if did not in seen.get("discussions", {}):
                    diff.new_discussions.append(dict(d))
                elif d["replies"] > seen["discussions"][did]:
                    diff.reply_growth.append(dict(d))
        elif kind == "assign":
            cmid = str(page["cmid"])
            item = {"cmid": cmid, "due_text": page["due_text"], "text_sha": _sha(page["text"]),
                    "title": page.get("title"), "url": page["url"]}
            old = seen.get("assigns", {}).get(cmid)
            if old is None:
                diff.new_assigns.append(item)
            elif old.get("due_text") != item["due_text"] or old.get("text_sha") != item["text_sha"]:
                diff.changed_assigns.append(item)
    return diff


def advance(seen: dict[str, Any], diff: Diff, ok_ids: set[str]) -> dict[str, Any]:
    """Return a copy of `seen` plus the diff items whose id is in `ok_ids`; never removes anything."""
    out = copy.deepcopy(seen)
    for key in _empty_seen():
        out.setdefault(key, {})
    for m in diff.new_modules:
        if str(m["cmid"]) in ok_ids:
            out["modules"][str(m["cmid"])] = {"name": m["name"], "type": m["type"], "section": m["section_id"]}
    for sec in diff.new_sections:
        if str(sec["id"]) in ok_ids:
            out["sections"][str(sec["id"])] = sec["name"]
    for d in diff.new_discussions + diff.reply_growth:
        if str(d["id"]) in ok_ids:
            out["discussions"][str(d["id"])] = d["replies"]
    for a in diff.new_assigns + diff.changed_assigns:
        if str(a["cmid"]) in ok_ids:
            out["assigns"][str(a["cmid"])] = {"due_text": a["due_text"], "text_sha": a["text_sha"]}
    return out
