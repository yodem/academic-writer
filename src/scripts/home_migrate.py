#!/usr/bin/env python3
"""Previewed, reversible migration to the home folder (stdlib only, Python 3.9+).

    python3 home_migrate.py --home DIR [--legacy DIR] [--daily-script PATH] [--workspace PATH ...]
                            [--data-dir DIR] [--launch-agents-dir DIR] [--reload-launchd] [--apply]

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
import os
import plistlib
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

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


# --- legacy path rewriting -----------------------------------------------------------------------

_NAME_CHARS = r"\w.\-~@+%"


def _legacy_prefixes(legacy_raw) -> list:
    """Every spelling of the legacy folder a file may carry: as given, expanded, resolved, ~/, $HOME/, ${HOME}/."""
    raw = str(legacy_raw)
    expanded = os.path.expandvars(os.path.expanduser(raw))
    cands = [raw, expanded]
    try:
        cands.append(str(Path(expanded).resolve()))
    except (OSError, RuntimeError):
        pass
    homedir = os.path.expanduser("~")
    if homedir and homedir != "/":
        for c in list(cands):
            if c.startswith(homedir + "/"):
                rel = c[len(homedir):]
                cands.extend(["~" + rel, "$HOME" + rel, "${HOME}" + rel])
    out: list = []
    for c in cands:
        c = c.rstrip("/")
        if c and c not in out:
            out.append(c)
    return sorted(out, key=len, reverse=True)


def _prefix_regex(prefixes: list) -> "re.Pattern":
    alt = "|".join(re.escape(p) for p in prefixes)
    # whole path component only: `<prefix>-other` / `<prefix>.json` / `x<prefix>` are left alone
    return re.compile(r"(?<![\w.\-/])(?:%s)(?:\.migrated-[0-9A-Za-z_-]+)?(?![%s])" % (alt, _NAME_CHARS))


def _json_inner(text: str) -> str:
    return json.dumps(text)[1:-1]


def _make_subs(legacy_raw, target: str) -> list:
    """[(regex, replacement)]: plain spelling, plus the ensure_ascii-escaped spelling when it differs."""
    prefixes = _legacy_prefixes(legacy_raw)
    subs = [(_prefix_regex(prefixes), target)]
    escaped = [_json_inner(p) for p in prefixes]
    if escaped != prefixes:
        subs.append((_prefix_regex(escaped), _json_inner(target)))
    return subs


def _subst(text: str, subs: list) -> tuple:
    total = 0
    for rx, repl in subs:
        text, n = rx.subn(lambda _m, r=repl: r, text)
        total += n
    return text, total


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            for x in _strings(v):
                yield x
    elif isinstance(obj, list):
        for v in obj:
            for x in _strings(v):
                yield x


def _scan_registry(root: Path, subs: list, target: str, check_base: Path) -> tuple:
    """(rewrites, warnings): rewrites = [(path, old_text, new_text, matches, missing)]. Raises MigrateError before any write."""
    rewrites: list = []
    warnings: list = []
    if not root.is_dir():
        return rewrites, warnings
    for p in _files(root):
        rel = p.relative_to(root)
        if p.suffix not in (".json", ".md") or ".bak-" in p.name:
            continue
        if "logs" in rel.parts[:-1] or "done" in rel.parts[:-1]:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            warnings.append("unreadable, skipped: %s" % p)
            continue
        new, n = _subst(text, subs)
        if not n:
            continue
        missing: list = []
        if p.suffix == ".json":
            try:
                json.loads(text)
            except ValueError:
                warnings.append("not valid JSON, skipped: %s" % p)
                continue
            try:
                parsed = json.loads(new)
            except ValueError as exc:
                raise MigrateError("rewriting %s would break its JSON (%s); nothing was written" % (p, exc))
            for value in _strings(parsed):
                if value == target or value.startswith(target + "/"):
                    if not (check_base / value[len(target):].lstrip("/")).exists():
                        missing.append(value)
        rewrites.append((p, text, new, n, missing))
    return rewrites, warnings


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

def _pointer_state(data_dir: Path, home: Path) -> str:
    """"done" when `<data_dir>/home.json` already names this home, "differs" for another pointer, else "missing"."""
    pointer = data_dir / homelib.POINTER_FILE
    if not pointer.is_file():
        return "missing"
    try:
        value = json.loads(pointer.read_text(encoding="utf-8")).get("path")
    except (ValueError, OSError, AttributeError):
        return "differs"
    if isinstance(value, str) and value and Path(value).expanduser() == home:
        return "done"
    return "differs"


def _launchctl_lines(label: Optional[str], plist: Path, uid: int) -> list:
    if not label:
        return []
    return [["launchctl", "bootout", "gui/%d/%s" % (uid, label)], ["launchctl", "bootstrap", "gui/%d" % uid, str(plist)]]


def _plan(home: Path, legacy: Path, daily: Optional[Path], workspaces: list, stamp: str,
          legacy_raw=None, data_dir: Optional[Path] = None, launch_dir: Optional[Path] = None) -> tuple:
    helper = home / homelib.DIR_NAME
    steps: list = []
    warnings: list = []
    terms = helper / "terms"
    subs = _make_subs(legacy_raw if legacy_raw is not None else legacy, str(terms))

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

    # set-home-pointer
    pointer = (data_dir / homelib.POINTER_FILE) if data_dir is not None else None
    if data_dir is None:
        note = "no plugin data dir (--data-dir or CLAUDE_PLUGIN_DATA): the home pointer was not recorded"
        steps.append({"kind": "set-home-pointer", "from": None, "to": None, "status": "skipped", "note": note})
        warnings.append(note)
    else:
        state = _pointer_state(data_dir, home)
        step = {"kind": "set-home-pointer", "from": str(home), "to": str(pointer),
                "status": "done" if state == "done" else "todo"}
        if state == "differs":
            step["backup"] = str(pointer) + ".bak-" + stamp
        steps.append(step)

    # copy-registry
    migrated = sorted(legacy.parent.glob(legacy.name + ".migrated-*")) if legacy.parent.is_dir() else []
    if legacy.is_dir():
        steps.append({"kind": "copy-registry", "from": str(legacy), "to": str(terms), "status": "todo",
                      "files": len(_files(legacy))})
    elif migrated:
        steps.append({"kind": "copy-registry", "from": str(legacy), "to": str(terms), "status": "done"})

    # rewrite-registry (a preview before the copy counts the legacy folder; afterwards the copy is scanned)
    scan_root = legacy if legacy.is_dir() else terms
    if scan_root.is_dir():
        rewrites, scan_warnings = _scan_registry(scan_root, subs, str(terms), scan_root)
        warnings.extend(scan_warnings)
        step = {"kind": "rewrite-registry", "from": str(scan_root), "to": str(terms),
                "status": "todo" if rewrites else "done"}
        if rewrites:
            step["files"] = len(rewrites)
            step["matches"] = sum(r[3] for r in rewrites)
            step["paths"] = [str(r[0].relative_to(scan_root)) for r in rewrites]
            missing = sorted({m for r in rewrites for m in r[4]})
            if missing:
                step["missing"] = missing
                warnings.append("%d rewritten path(s) point at files that do not exist" % len(missing))
        steps.append(step)

    # daily-script
    if daily is not None and daily.is_file():
        text = daily.read_text(encoding="utf-8")
        has_export = _EXPORT in text
        new = _rewrite_daily(text, home) if (not has_export and _TERM_LINE_RE.search(text)) else text
        new, n = _subst(new, subs)
        if has_export and new == text:
            steps.append({"kind": "daily-script", "from": str(daily), "to": str(daily), "status": "done"})
        elif new != text:
            steps.append({"kind": "daily-script", "from": str(daily), "to": str(daily), "status": "todo",
                          "diff": _diff(text, new, daily.name), "_text": new})

    # helper-scripts: every other *.sh beside the daily script (sync script SRC, lock script DIR)
    if daily is not None and daily.parent.is_dir():
        others = [p for p in sorted(daily.parent.glob("*.sh")) if p.is_file() and p.name != daily.name]
        todo = []
        for p in others:
            text = p.read_text(encoding="utf-8")
            new, n = _subst(text, subs)
            if n:
                todo.append({"kind": "helper-scripts", "from": str(p), "to": str(p), "status": "todo",
                             "diff": _diff(text, new, p.name), "backup": str(p) + ".bak-" + stamp, "_text": new})
        if todo:
            steps.extend(todo)
        elif others:
            steps.append({"kind": "helper-scripts", "from": str(daily.parent), "to": str(daily.parent), "status": "done"})

    # launchd-plist
    reload_lines: list = []
    if launch_dir is not None and launch_dir.is_dir():
        uid = os.getuid() if hasattr(os, "getuid") else 0
        for p in sorted(launch_dir.glob("*.plist")):
            try:
                text = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            names_daily = daily is not None and (str(daily) in text or "/" + daily.name in text)
            new, n = _subst(text, subs)
            if not (n or names_daily):
                continue
            try:
                label = plistlib.loads(text.encode("utf-8")).get("Label")
            except Exception:
                warnings.append("not a valid plist, skipped: %s" % p)
                continue
            if n:
                try:
                    plistlib.loads(new.encode("utf-8"))
                except Exception as exc:
                    raise MigrateError("rewriting %s would break the plist (%s); nothing was written" % (p, exc))
                steps.append({"kind": "launchd-plist", "from": str(p), "to": str(p), "status": "todo", "label": label,
                              "diff": _diff(text, new, p.name), "backup": str(p) + ".bak-" + stamp, "_text": new})
                lines = _launchctl_lines(label, p, uid)
                if lines:
                    reload_lines.append({"label": label, "plist": str(p), "commands": lines, "ran": False})
                else:
                    warnings.append("%s has no Label; reload it by hand" % p)
            else:
                steps.append({"kind": "launchd-plist", "from": str(p), "to": str(p), "status": "done", "label": label})

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

    order = {"write-home": 0, "set-home-pointer": 1, "copy-registry": 2, "rewrite-registry": 3, "daily-script": 4,
             "helper-scripts": 5, "launchd-plist": 6, "shrink-profile": 7, "register": 8}
    steps.sort(key=lambda s: order[s["kind"]])  # stable: workspace order is kept inside a kind
    return steps, warnings, reload_lines, subs


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


def _rewrite_registry(terms: Path, subs: list, stamp: str) -> list:
    rewrites, _warn = _scan_registry(terms, subs, str(terms), terms)  # validates every file before any write
    for path, _old, new, _n, _missing in rewrites:
        _backup(path, stamp)
        homelib._atomic_write(path, new)
    return rewrites


def _apply(steps: list, home: Path, legacy: Path, stamp: str, data_dir: Optional[Path] = None,
           subs: Optional[list] = None) -> None:
    helper = home / homelib.DIR_NAME
    for step in steps:
        if step["status"] != "todo":
            continue
        kind = step["kind"]
        if kind == "write-home":
            helper.mkdir(parents=True, exist_ok=True)
            homelib._atomic_write(helper / homelib.HOME_FILE, step["_text"])
        elif kind == "set-home-pointer":
            pointer = Path(step["to"])
            if pointer.is_file():
                _backup(pointer, stamp)
            homelib.set_home(home, data_dir)
        elif kind == "copy-registry":
            _copy_registry(legacy, helper / "terms", stamp)
        elif kind == "rewrite-registry":
            done = _rewrite_registry(helper / "terms", subs, stamp)
            step["files"] = len(done)
            step["matches"] = sum(r[3] for r in done)
            step.pop("missing", None)
            missing = sorted({m for r in done for m in r[4]})
            if missing:
                step["missing"] = missing
        elif kind in ("daily-script", "helper-scripts", "launchd-plist", "shrink-profile"):
            path = Path(step["from"])
            _backup(path, stamp)
            homelib._atomic_write(path, step["_text"])
        elif kind == "register":
            ws, ws_type, course, term = step["_args"]
            helper.mkdir(parents=True, exist_ok=True)
            homelib.register_workspace(home, ws, ws_type, course, term)
        step["status"] = "done"


def _run_launchctl(cmd: list) -> int:
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode


def migrate(home: Path, legacy: Optional[Path] = None, daily_script: Optional[Path] = None,
            workspaces: Optional[list] = None, apply: bool = False, stamp: Optional[str] = None,
            data_dir: Optional[Path] = None, launch_agents_dir: Optional[Path] = None,
            reload_launchd: bool = False, runner: Optional[Callable] = None) -> dict:
    home = Path(home).expanduser()
    legacy_raw = legacy if legacy is not None else DEFAULT_LEGACY
    legacy = Path(legacy_raw).expanduser()
    daily = Path(daily_script).expanduser() if daily_script else None
    wss = [Path(w).expanduser() for w in (workspaces or [])]
    data = Path(data_dir).expanduser() if data_dir else None
    launch = Path(launch_agents_dir).expanduser() if launch_agents_dir else None
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M")
    steps, warnings, reload_lines, subs = _plan(home, legacy, daily, wss, stamp, legacy_raw=legacy_raw,
                                                data_dir=data, launch_dir=launch)
    if apply:
        _apply(steps, home, legacy, stamp, data_dir=data, subs=subs)
        if reload_launchd and reload_lines:
            run = runner or _run_launchctl
            for item in reload_lines:
                item["returncodes"] = [run(list(cmd)) for cmd in item["commands"]]
                item["ran"] = True
    return {"steps": [{k: v for k, v in s.items() if not k.startswith("_")} for s in steps],
            "warnings": warnings, "reload": reload_lines}


def _main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="Migrate to the home folder (preview unless --apply)")
    ap.add_argument("--home", required=True)
    ap.add_argument("--legacy", default=None)
    ap.add_argument("--daily-script", default=None)
    ap.add_argument("--workspace", action="append", default=[])
    ap.add_argument("--data-dir", default=None, help="plugin data dir for the home pointer (default: $CLAUDE_PLUGIN_DATA)")
    ap.add_argument("--launch-agents-dir", default="~/Library/LaunchAgents")
    ap.add_argument("--reload-launchd", action="store_true", help="with --apply on macOS: bootout and bootstrap the rewritten plists")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    if args.reload_launchd and not (args.apply and sys.platform == "darwin"):
        print(json.dumps({"error": "--reload-launchd needs --apply and macOS"}, ensure_ascii=False))
        return 2
    data_dir = args.data_dir or os.environ.get("CLAUDE_PLUGIN_DATA") or None
    try:
        plan = migrate(Path(args.home), Path(args.legacy) if args.legacy else None,
                       Path(args.daily_script) if args.daily_script else None,
                       [Path(w) for w in args.workspace], apply=args.apply,
                       data_dir=Path(data_dir) if data_dir else None,
                       launch_agents_dir=Path(args.launch_agents_dir), reload_launchd=args.reload_launchd)
    except MigrateError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    for w in plan["warnings"]:
        print("warning: " + w, file=sys.stderr)
    for item in plan["reload"]:
        if not item["ran"]:
            print("to reload %s run:" % item["label"], file=sys.stderr)
            for cmd in item["commands"]:
                print("  " + " ".join(cmd), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
