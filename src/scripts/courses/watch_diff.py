"""Pure seen-state diff for the Chrome-driven Lemida watcher (T1).

No I/O, no network. Pages are plain dicts (see the plan's PageData model); `seen` is
{"modules": {cmid: {...}}, "discussions": {id: reply_count}, "assigns": {cmid: {...}}, "sections": {id: name}}.
"""
from __future__ import annotations

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


def validate_page(data: dict[str, Any]) -> None:
    raise NotImplementedError


def baseline(pages: list[dict[str, Any]]) -> dict[str, Any]:
    raise NotImplementedError


def diff_course(pages: list[dict[str, Any]], seen: dict[str, Any], *, legacy_seen: dict[str, Any] | None = None,
                sources: list[dict[str, Any]] | None = None) -> Diff:
    raise NotImplementedError


def advance(seen: dict[str, Any], diff: Diff, ok_ids: set[str]) -> dict[str, Any]:
    raise NotImplementedError
