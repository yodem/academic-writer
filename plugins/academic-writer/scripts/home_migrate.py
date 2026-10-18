#!/usr/bin/env python3
"""Previewed, reversible migration to the home folder (stdlib only, Python 3.9+).

    python3 home_migrate.py --home DIR [--legacy DIR] [--daily-script PATH] [--workspace PATH ...] [--apply]

Without --apply it prints a JSON plan {steps: [{kind, from, to, diff?, status}]} and changes nothing.
With --apply it runs the steps that are still "todo". Nothing is ever deleted or overwritten: the legacy registry is
renamed (not removed), edited files get a `.bak-<stamp>` copy first, and a destination file that differs from the
source stops the run before anything moves. No model call, no network.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import home as homelib  # noqa: E402

IDENTITY_KEYS = ("name", "author_key", "role", "institution", "degree", "fieldOfStudy", "citationStyle",
                 "targetLanguage", "abstractLanguages", "createdAt", "updatedAt")
DEFAULT_LEGACY = "~/.academic-writer/courses"
_FM_RE = re.compile(r"^---\n([\s\S]*?)\n---")
_SECTION_RE = re.compile(r"^## ([^\n]+)\n+```json\n([\s\S]*?)\n```\n?", re.M)
_TERM_LINE_RE = re.compile(r'^TERM_DIR="\$\{COURSES_TERM_DIR:-(.*)\}"[ \t]*$', re.M)
_EXPORT = "export ACADEMIC_HOME="


class MigrateError(Exception):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _files(root: Path) -> list:
    return sorted(p for p in root.rglob("*") if p.is_file())


def _unique(path: Path) -> Path:
    """`path`, or `path-2`, `path-3`... so an existing backup is never overwritten."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name("%s-%d" % (path.name, n))
        if not candidate.exists():
            return candidate
        n += 1


def _backup(path: Path, stamp: str) -> Path:
    target = _unique(path.with_name(path.name + ".bak-" + stamp))
    shutil.copy2(str(path), str(target))
    return target


def _diff(old: str, new: str, name: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), "a/" + name, "b/" + name))


# --- frontmatter helpers ----------------------------------------------------------------------

def _split_groups(front: str) -> list:
    """Frontmatter lines grouped as (key | None, [lines]); a list key owns its `  - item` lines."""
    lines = front.split("\n")
    groups: list = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^[\w-]+: .+$", line):
            groups.append((line.split(":")[0], [line]))
            i += 1
        elif re.match(r"^[\w-]+:\s*$", line):
            block = [line]
            i += 1
            while i < len(lines) and lines[i].startswith("  - "):
                block.append(lines[i])
                i += 1
            groups.append((line.split(":")[0], block))
        else:
            groups.append((None, [line]))
            i += 1
    return groups


def _ws_type(values: dict) -> str:
    declared = values.get("workspace")
    if declared in homelib.WORKSPACE_TYPES:
        return declared
    return "course" if values.get("course") else "project"


def _shrink_text(text: str, home_values: dict, home_sections: dict, ws_type: str) -> str:
    m = _FM_RE.match(text)
    front, rest = (m.group(1), text[m.end():]) if m else ("", "\n\n" + text if text else "\n")
    kept: list = []
    for key, block in _split_groups(front):
        if key is not None and key in home_values and homelib.read_frontmatter("---\n" + "\n".join(block) + "\n---").get(key) == home_values[key]:
            continue
        if key is None and not block[0].strip():
            continue
        kept.extend(block)
    kept.append("workspace: " + ws_type)

    def drop_equal(match: "re.Match") -> str:
        key = re.sub(r"\s+", "", match.group(1).strip().lower())
        try:
            value = json.loads(match.group(2))
        except ValueError:
            return match.group(0)
        return "" if key in home_sections and home_sections[key] == value else match.group(0)

    rest = _SECTION_RE.sub(drop_equal, rest)
    return "---\n" + "\n".join(kept) + "\n---" + rest


def _home_md_text(profile_texts: list) -> str:
    """Identity keys whose value is equal in EVERY profile; a key that differs or is missing in any of them stays
    in each workspace profile, so no workspace inherits a value it never had."""
    parsed = [homelib.read_frontmatter(t) for t in profile_texts]
    m = _FM_RE.match(profile_texts[0]) if profile_texts else None
    lines: list = []
    if m:
        for key, block in _split_groups(m.group(1)):
            if key in IDENTITY_KEYS and all(key in v and v[key] == parsed[0][key] for v in parsed):
                lines.extend(block)
    return "---\n" + "\n".join(lines) + "\n---\n"


# --- plan --------------------------------------------------------------------------------------

def _plan(home: Path, legacy: Path, daily: Optional[Path], workspaces: list, stamp: str) -> list:
    helper = home / homelib.DIR_NAME
    steps: list = []

    profiles = []
    for ws in workspaces:
        path = ws / homelib.DIR_NAME / homelib.PROFILE_FILE
        if path.is_file():
            profiles.append((ws, path, path.read_text(encoding="utf-8")))

    # write-home
    home_md = helper / homelib.HOME_FILE
    if home_md.is_file():
        home_values = homelib.read_frontmatter(home_md.read_text(encoding="utf-8"))
        home_sections = homelib.read_sections(home_md.read_text(encoding="utf-8"))
        steps.append({"kind": "write-home", "from": None, "to": str(home_md), "status": "done"})
    else:
        home_values, home_sections = {}, {}
        if profiles:
            candidate = _home_md_text([text for _ws, _path, text in profiles])
            values = homelib.read_frontmatter(candidate)
            if values:
                home_values = values
                steps.append({"kind": "write-home", "from": str(profiles[0][1]), "to": str(home_md),
                              "status": "todo", "diff": _diff("", candidate, "home.md"), "_text": candidate})

    # copy-registry
    terms = helper / "terms"
    migrated = sorted(legacy.parent.glob(legacy.name + ".migrated-*")) if legacy.parent.is_dir() else []
    if legacy.is_dir():
        steps.append({"kind": "copy-registry", "from": str(legacy), "to": str(terms), "status": "todo",
                      "files": len(_files(legacy))})
    elif migrated:
        steps.append({"kind": "copy-registry", "from": str(legacy), "to": str(terms), "status": "done"})

    # daily-script
    if daily is not None and daily.is_file():
        text = daily.read_text(encoding="utf-8")
        if _EXPORT in text:
            steps.append({"kind": "daily-script", "from": str(daily), "to": str(daily), "status": "done"})
        elif _TERM_LINE_RE.search(text):
            new = _rewrite_daily(text, home)
            steps.append({"kind": "daily-script", "from": str(daily), "to": str(daily), "status": "todo",
                          "diff": _diff(text, new, daily.name), "_text": new})

    # shrink-profile and register
    rows = {r.get("path") for r in homelib.list_workspaces(home)} if (helper / homelib.WORKSPACES_FILE).is_file() else set()
    for ws, path, text in profiles:
        values = homelib.read_frontmatter(text)
        ws_type = _ws_type(values)
        if "workspace" in values:
            steps.append({"kind": "shrink-profile", "from": str(path), "to": str(path), "status": "done"})
        else:
            new = _shrink_text(text, home_values, home_sections, ws_type)
            steps.append({"kind": "shrink-profile", "from": str(path), "to": str(path), "status": "todo",
                          "diff": _diff(text, new, path.name), "backup": str(path) + ".bak-" + stamp, "_text": new})
        resolved = str(ws.resolve())
        steps.append({"kind": "register", "from": str(ws), "to": str(helper / homelib.WORKSPACES_FILE),
                      "status": "done" if resolved in rows else "todo",
                      "_args": (ws, ws_type, values.get("course"), values.get("term"))})

    order = {"write-home": 0, "copy-registry": 1, "daily-script": 2, "shrink-profile": 3, "register": 4}
    steps.sort(key=lambda s: order[s["kind"]])  # stable: workspace order is kept inside a kind
    return steps


def _rewrite_daily(text: str, home: Path) -> str:
    def repl(m: "re.Match") -> str:
        name = m.group(1).rstrip("/").split("/")[-1]
        tail = "" if name in ("", "courses") else "/" + name
        return ('%s"${ACADEMIC_HOME:-%s}"\nTERM_DIR="${COURSES_TERM_DIR:-$ACADEMIC_HOME/.academic-helper/terms%s}"'
                % (_EXPORT, home, tail))
    return _TERM_LINE_RE.sub(repl, text, count=1)


# --- apply -------------------------------------------------------------------------------------

def _copy_registry(legacy: Path, terms: Path, stamp: str) -> None:
    files = _files(legacy)
    for src in files:  # preflight: stop before anything moves
        dest = terms / src.relative_to(legacy)
        if dest.exists() and _sha(dest) != _sha(src):
            raise MigrateError("%s already exists and differs from %s; nothing was moved" % (dest, src))
    for src in files:
        dest = terms / src.relative_to(legacy)
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))
    for src in files:
        dest = terms / src.relative_to(legacy)
        if not dest.is_file() or _sha(dest) != _sha(src):
            raise MigrateError("copy of %s could not be verified; the legacy folder was left in place" % src)
    target = _unique(legacy.with_name(legacy.name + ".migrated-" + stamp))
    legacy.rename(target)


def _apply(steps: list, home: Path, legacy: Path, stamp: str) -> None:
    helper = home / homelib.DIR_NAME
    for step in steps:
        if step["status"] != "todo":
            continue
        kind = step["kind"]
        if kind == "write-home":
            helper.mkdir(parents=True, exist_ok=True)
            homelib._atomic_write(helper / homelib.HOME_FILE, step["_text"])
        elif kind == "copy-registry":
            _copy_registry(legacy, helper / "terms", stamp)
        elif kind == "daily-script":
            path = Path(step["from"])
            _backup(path, stamp)
            homelib._atomic_write(path, step["_text"])
        elif kind == "shrink-profile":
            path = Path(step["from"])
            _backup(path, stamp)
            homelib._atomic_write(path, step["_text"])
        elif kind == "register":
            ws, ws_type, course, term = step["_args"]
            helper.mkdir(parents=True, exist_ok=True)
            homelib.register_workspace(home, ws, ws_type, course, term)
        step["status"] = "done"


def migrate(home: Path, legacy: Optional[Path] = None, daily_script: Optional[Path] = None,
            workspaces: Optional[list] = None, apply: bool = False, stamp: Optional[str] = None) -> dict:
    home = Path(home).expanduser()
    legacy = Path(legacy if legacy is not None else DEFAULT_LEGACY).expanduser()
    daily = Path(daily_script).expanduser() if daily_script else None
    wss = [Path(w).expanduser() for w in (workspaces or [])]
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M")
    steps = _plan(home, legacy, daily, wss, stamp)
    if apply:
        _apply(steps, home, legacy, stamp)
    return {"steps": [{k: v for k, v in s.items() if not k.startswith("_")} for s in steps]}


def _main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="Migrate to the home folder (preview unless --apply)")
    ap.add_argument("--home", required=True)
    ap.add_argument("--legacy", default=None)
    ap.add_argument("--daily-script", default=None)
    ap.add_argument("--workspace", action="append", default=[])
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    try:
        plan = migrate(Path(args.home), Path(args.legacy) if args.legacy else None,
                       Path(args.daily_script) if args.daily_script else None,
                       [Path(w) for w in args.workspace], apply=args.apply)
    except MigrateError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
