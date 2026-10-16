"""Pure seen-state diff for the Chrome-driven Lemida watcher (T1).

No I/O, no network. Pages are plain dicts (see the plan's PageData model); `seen` is
{"modules": {cmid: {...}}, "discussions": {id: reply_count}, "assigns": {cmid: {...}}, "sections": {id: name}}.
"""
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from typing import Any


INGESTED_STATUSES = frozenset({"queued", "done"})
# `--ok` kinds: a module and an assignment share one cmid space, discussions and sections have their own.
OK_KINDS = ("module", "assign", "discussion", "section")
_CMID_KINDS = frozenset({"module", "assign"})


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
    # A source counts as seen only once its ingest finished (courses.py add-source reaches "queued" after
    # Drive and NotebookLM both succeeded); drive_done/uploaded ones must resurface so the retry happens.
    known |= {str(s["origin_ref"])[3:] for s in (sources or [])
              if str(s.get("origin_ref", "")).startswith("cm:") and s.get("status") in INGESTED_STATUSES}
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


def _diff_ids(diff: Diff) -> dict[str, set[str]]:
    return {
        "module": {str(m["cmid"]) for m in diff.new_modules},
        "assign": {str(a["cmid"]) for a in diff.new_assigns + diff.changed_assigns},
        "discussion": {str(d["id"]) for d in diff.new_discussions + diff.reply_growth},
        "section": {str(sec["id"]) for sec in diff.new_sections},
    }


def resolve_ok(diff: Diff, ok_ids: set[str]) -> set[tuple[str, str]]:
    """Turn `--ok` tokens into (kind, id) pairs.

    Tokens are `module:42`, `assign:42`, `discussion:42` or `section:7`. A bare `42` is accepted only when it
    names exactly one kind in the diff (a module and its assignment share a cmid and count as one kind);
    otherwise it is rejected as ambiguous so one id never acknowledges two unrelated entities.
    """
    ids = _diff_ids(diff)
    out: set[tuple[str, str]] = set()
    for token in sorted(str(t) for t in ok_ids):
        kind, sep, ident = token.partition(":")
        if sep:
            if kind not in OK_KINDS:
                raise WatchSchemaError(f"unknown --ok kind {kind!r} in {token!r}; use one of {', '.join(OK_KINDS)}")
            out.add((kind, ident))
            continue
        hits = [k for k in OK_KINDS if token in ids[k]]
        if len({"cmid" if k in _CMID_KINDS else k for k in hits}) > 1:
            raise WatchSchemaError(f"ambiguous --ok id {token!r} matches {', '.join(hits)}; "
                                   f"say which: " + " or ".join(f"{k}:{token}" for k in hits))
        out.update((k, token) for k in hits)
    return out


def advance(seen: dict[str, Any], diff: Diff, ok_ids: set[str]) -> dict[str, Any]:
    """Return a copy of `seen` plus the diff items acknowledged by `ok_ids` (see resolve_ok); never removes anything."""
    ok = resolve_ok(diff, ok_ids)
    out = copy.deepcopy(seen)
    for key in _empty_seen():
        out.setdefault(key, {})
    for m in diff.new_modules:
        if ("module", str(m["cmid"])) in ok:
            out["modules"][str(m["cmid"])] = {"name": m["name"], "type": m["type"], "section": m["section_id"]}
    for sec in diff.new_sections:
        if ("section", str(sec["id"])) in ok:
            out["sections"][str(sec["id"])] = sec["name"]
    for d in diff.new_discussions + diff.reply_growth:
        if ("discussion", str(d["id"])) in ok:
            out["discussions"][str(d["id"])] = d["replies"]
    for a in diff.new_assigns + diff.changed_assigns:
        if ("assign", str(a["cmid"])) in ok:
            out["assigns"][str(a["cmid"])] = {"due_text": a["due_text"], "text_sha": a["text_sha"]}
    return out
