#!/usr/bin/env python3
"""Home folder pointer, profile merge and workspace registry (stdlib only, Python 3.9+).

The home folder holds `<home>/.academic-helper/home.md` (the author's identity and defaults), `workspaces.json`
and `terms/`. A workspace folder holds `.academic-helper/profile.md`, which overrides the home values.
No model call, no network. Writes only the pointer file, the home's `.academic-helper/` folder and `workspaces.json`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional

ROLES = ("student", "lecturer", "researcher")
WORKSPACE_TYPES = ("course", "project", "teaching")

DIR_NAME = ".academic-helper"
HOME_FILE = "home.md"
PROFILE_FILE = "profile.md"
WORKSPACES_FILE = "workspaces.json"
POINTER_FILE = "home.json"

_FM_RE = re.compile(r"^---\n([\s\S]*?)\n---")
_KV_RE = re.compile(r"^([\w-]+): (.+)$")
_LIST_KEY_RE = re.compile(r"^[\w-]+:\s*$")
_SECTION_RE = re.compile(r"^## ([^\n]+)\n+```json\n([\s\S]*?)\n```", re.M)


def read_frontmatter(text: str) -> dict:
    """Scalars, `null`, `[]` and `  - item` lists; the same rules as src/hooks/src/lib/profile.ts."""
    out: dict = {}
    match = _FM_RE.match(text)
    if not match:
        return out
    lines = match.group(1).split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        kv = _KV_RE.match(line)
        if kv:
            key, value = kv.group(1), kv.group(2).strip()
            if value == "null":
                out[key] = None
            elif value == "[]":
                out[key] = []
            else:
                out[key] = value
            i += 1
        elif _LIST_KEY_RE.match(line):
            key = line.split(":")[0]
            items = []
            i += 1
            while i < len(lines) and lines[i].startswith("  - "):
                items.append(lines[i][4:])
                i += 1
            out[key] = items
        else:
            i += 1
    return out


def read_sections(text: str) -> dict:
    """`## Heading` + a json block; key = heading lowercased without spaces. Malformed JSON is skipped."""
    out: dict = {}
    for m in _SECTION_RE.finditer(text):
        key = re.sub(r"\s+", "", m.group(1).strip().lower())
        try:
            out[key] = json.loads(m.group(2))
        except ValueError:
            continue
    return out


def _pointer_path(plugin_data: Path) -> Path:
    return plugin_data / POINTER_FILE


def home_dir(env: Optional[Mapping[str, str]] = None) -> Optional[Path]:
    """ACADEMIC_HOME, then $CLAUDE_PLUGIN_DATA/home.json {"path": ...}, else None. Never raises."""
    try:
        e = os.environ if env is None else env
        explicit = e.get("ACADEMIC_HOME")
        if explicit:
            return Path(explicit).expanduser()
        data = e.get("CLAUDE_PLUGIN_DATA")
        if data:
            pointer = _pointer_path(Path(data))
            if pointer.is_file():
                value = json.loads(pointer.read_text(encoding="utf-8")).get("path")
                if isinstance(value, str) and value:
                    return Path(value).expanduser()
    except Exception:
        return None
    return None


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def set_home(path: Path, plugin_data: Path) -> None:
    """Write the pointer atomically; create `<path>/.academic-helper/` only."""
    path = Path(path).expanduser()
    (path / DIR_NAME).mkdir(parents=True, exist_ok=True)
    _atomic_write(_pointer_path(Path(plugin_data)), json.dumps({"path": str(path)}, ensure_ascii=False) + "\n")


@dataclass
class ResolvedProfile:
    values: dict = field(default_factory=dict)
    sections: dict = field(default_factory=dict)
    home: Optional[Path] = None
    home_missing: bool = False
    workspace_type: Optional[str] = None
    course: Optional[str] = None
    term: Optional[str] = None


def _read_md(path: Path) -> tuple:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}, {}
    return read_frontmatter(text), read_sections(text)


def resolve_profile(workspace: Path, env: Optional[Mapping[str, str]] = None) -> ResolvedProfile:
    """home.md values, then the workspace profile.md overrides (frontmatter keys and whole JSON sections)."""
    home = home_dir(env)
    values: dict = {}
    sections: dict = {}
    home_missing = False
    if home is not None:
        if home.is_dir():
            values, sections = _read_md(home / DIR_NAME / HOME_FILE)
        else:
            home_missing = True
    w_values, w_sections = _read_md(Path(workspace) / DIR_NAME / PROFILE_FILE)
    values.update(w_values)
    sections.update(w_sections)

    def _str(key: str) -> Optional[str]:
        v = values.get(key)
        return v if isinstance(v, str) and v else None

    return ResolvedProfile(values=values, sections=sections, home=home, home_missing=home_missing,
                           workspace_type=_str("workspace"), course=_str("course"), term=_str("term"))


def _workspaces_path(home: Path) -> Path:
    return Path(home) / DIR_NAME / WORKSPACES_FILE


def _load_rows(home: Path) -> list:
    try:
        rows = json.loads(_workspaces_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return rows if isinstance(rows, list) else []


def register_workspace(home: Path, path: Path, type: str, course: Optional[str] = None,
                       term: Optional[str] = None) -> dict:
    """Upsert by resolved path into <home>/.academic-helper/workspaces.json."""
    if type not in WORKSPACE_TYPES:
        raise ValueError("type must be one of %s" % ", ".join(WORKSPACE_TYPES))
    resolved = str(Path(path).expanduser().resolve())
    rows = _load_rows(home)
    for row in rows:
        if isinstance(row, dict) and row.get("path") == resolved:
            row.update({"type": type, "course": course, "term": term})
            result = row
            break
    else:
        result = {"path": resolved, "type": type, "course": course, "term": term,
                  "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        rows.append(result)
    _atomic_write(_workspaces_path(home), json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    return result


def list_workspaces(home: Path) -> list:
    """Every registered row plus `exists`; a moved or deleted folder is flagged, never dropped."""
    return [dict(row, exists=Path(row["path"]).is_dir())
            for row in _load_rows(home) if isinstance(row, dict) and row.get("path")]


def _main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="Home folder pointer and workspace registry")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    p_set = sub.add_parser("set")
    p_set.add_argument("--path", required=True)
    p_reg = sub.add_parser("register")
    p_reg.add_argument("--path", required=True)
    p_reg.add_argument("--type", required=True, choices=WORKSPACE_TYPES)
    p_reg.add_argument("--course")
    p_reg.add_argument("--term")
    args = ap.parse_args(argv)

    if args.cmd == "show":
        h = home_dir()
        out: dict = {"home": str(h) if h else None, "exists": bool(h and h.is_dir()), "workspaces": []}
        if h and h.is_dir():
            out["workspaces"] = list_workspaces(h)
    elif args.cmd == "set":
        data = os.environ.get("CLAUDE_PLUGIN_DATA")
        if not data:
            print(json.dumps({"error": "CLAUDE_PLUGIN_DATA is not set"}))
            return 2
        set_home(Path(args.path), Path(data))
        out = {"home": str(Path(args.path).expanduser())}
    else:
        h = home_dir()
        if h is None:
            print(json.dumps({"error": "no home folder is set"}))
            return 2
        out = register_workspace(h, Path(args.path), args.type, args.course, args.term)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
