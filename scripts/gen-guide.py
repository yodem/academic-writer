#!/usr/bin/env python3
"""Regenerate the command lists in the HTML guide and the help skill from skill frontmatter.

Sources of truth:
  - src/skills/*/SKILL.md frontmatter (name, user-invocable, description, metadata.summary)
  - manifests/academic-writer.json (version)

Targets (only the text between the markers is rewritten):
  - src/guide/index.html      <!-- guide:commands:start --> ... <!-- guide:commands:end -->
                              <!-- guide:version:start --> ... <!-- guide:version:end -->
  - src/skills/help/SKILL.md  <!-- help:commands:start --> ... <!-- help:commands:end -->

Usage:
  python3 scripts/gen-guide.py            # rewrite in place (idempotent)
  python3 scripts/gen-guide.py --check    # exit 1 if any target would change
  python3 scripts/gen-guide.py --root DIR # operate on another checkout (used by tests)

Standard library only: the build must not depend on PyYAML.
"""
from __future__ import annotations

import argparse
import difflib
import html
import json
import re
import sys
from pathlib import Path

PREFIX = "/academic-writer:"

# Recommended order: first-run commands first, then the writing loop, then tools.
# Anything not listed here is appended alphabetically.
ORDER = [
    "intro", "setup", "init", "write", "revise", "edit", "edit-section",
    "proofread", "review", "research", "ideate", "ocr", "voice", "health", "help",
]


# ---------------------------------------------------------------------------
# Minimal frontmatter reader (the subset our SKILL.md files use)
# ---------------------------------------------------------------------------

def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        if value[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        else:
            inner = inner.replace("''", "'")
        return inner
    return value


def _split_flow(body: str) -> list[str]:
    """Split the inside of a {..} or [..] flow collection on top-level commas."""
    parts, buf, quote, depth = [], [], "", 0
    for ch in body:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if "".join(buf).strip():
        parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _scalar(value: str):
    value = value.strip()
    if value.startswith("{") and value.endswith("}"):
        out = {}
        for item in _split_flow(value[1:-1]):
            if ":" in item:
                k, v = item.split(":", 1)
                out[_unquote(k)] = _scalar(v)
        return out
    if value.startswith("[") and value.endswith("]"):
        return [_scalar(v) for v in _split_flow(value[1:-1])]
    low = value.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    return _unquote(value)


def _block(lines: list[str], style: str) -> str:
    stripped = [ln.strip() for ln in lines]
    if style.startswith("|"):
        return "\n".join(stripped).strip()
    return " ".join(s for s in stripped if s).strip()


def parse_frontmatter(text: str) -> dict:
    m = re.match(r"---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return {}
    lines = m.group(1).splitlines()
    data: dict = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        km = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not km:
            i += 1
            continue
        key, rest = km.group(1), km.group(2)
        # Collect indented continuation lines.
        cont = []
        j = i + 1
        while j < len(lines) and (lines[j].startswith((" ", "\t")) or not lines[j].strip()):
            cont.append(lines[j])
            j += 1
        if rest in ("", ">", ">-", "|", "|-", ">+", "|+"):
            nonblank = [c for c in cont if c.strip()]
            if rest and rest[0] in ">|":
                data[key] = _block(cont, rest)
            elif nonblank and all(re.match(r"^\s+-\s", c) for c in nonblank):
                data[key] = [_scalar(re.sub(r"^\s+-\s", "", c)) for c in nonblank]
            elif nonblank:
                sub = {}
                for c in nonblank:
                    sm = re.match(r"^\s+([A-Za-z0-9_-]+):\s*(.*)$", c)
                    if sm:
                        sub[sm.group(1)] = _scalar(sm.group(2))
                data[key] = sub
            else:
                data[key] = ""
        else:
            value = rest
            if cont and not value.strip().startswith(("{", "[")) and value.strip()[:1] not in "\"'":
                # Plain multi-line scalar.
                value = " ".join([value] + [c.strip() for c in cont if c.strip()])
            elif cont and value.strip()[:1] in "\"'{[":
                joined = " ".join([value] + [c.strip() for c in cont if c.strip()])
                value = joined
            data[key] = _scalar(value)
        i = j
    return data


# ---------------------------------------------------------------------------
# Command list
# ---------------------------------------------------------------------------

def first_sentence(text: str) -> str:
    text = " ".join(str(text).split())
    m = re.search(r"(?<!\be\.g)(?<!\bi\.e)(?<!\betc)[.!?](\s|$)", text)
    return text[: m.start() + 1] if m else text


def summary_for(fm: dict) -> str:
    meta = fm.get("metadata")
    if isinstance(meta, dict) and str(meta.get("summary", "")).strip():
        return " ".join(str(meta["summary"]).split())
    return first_sentence(fm.get("description", ""))


def load_commands(root: Path) -> list[tuple[str, str]]:
    cmds = []
    for path in sorted((root / "src/skills").glob("*/SKILL.md")):
        fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        if fm.get("user-invocable") is not True:
            continue
        name = str(fm.get("name") or path.parent.name)
        cmds.append((name, summary_for(fm)))
    rank = {n: i for i, n in enumerate(ORDER)}
    cmds.sort(key=lambda c: (rank.get(c[0], len(ORDER)), c[0]))
    return cmds


def guide_block(cmds) -> str:
    rows = ["<table class=\"commands\">",
            "<thead><tr><th scope=\"col\">Command</th><th scope=\"col\">What it does</th></tr></thead>",
            "<tbody>"]
    for name, summary in cmds:
        rows.append(
            f"<tr><td><code>{html.escape(PREFIX + name)}</code></td>"
            f"<td>{html.escape(summary)}</td></tr>"
        )
    rows += ["</tbody>", "</table>"]
    return "\n" + "\n".join(rows) + "\n"


def help_block(cmds) -> str:
    rows = ["| Command | What it does |", "|---|---|"]
    for name, summary in cmds:
        rows.append(f"| `{PREFIX}{name}` | {summary.replace('|', '/')} |")
    return "\n" + "\n".join(rows) + "\n"


def replace_between(text: str, start: str, end: str, body: str, label: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pattern.search(text):
        raise SystemExit(f"gen-guide: markers {start} / {end} not found in {label}")
    return pattern.sub(lambda _m: start + body + end, text, count=1)


def render(root: Path) -> dict[Path, str]:
    version = json.loads((root / "manifests/academic-writer.json").read_text(encoding="utf-8"))["version"]
    cmds = load_commands(root)
    guide = root / "src/guide/index.html"
    help_md = root / "src/skills/help/SKILL.md"
    g = guide.read_text(encoding="utf-8")
    g = replace_between(g, "<!-- guide:commands:start -->", "<!-- guide:commands:end -->",
                        guide_block(cmds), str(guide))
    g = replace_between(g, "<!-- guide:version:start -->", "<!-- guide:version:end -->",
                        html.escape(version), str(guide))
    h = help_md.read_text(encoding="utf-8")
    h = replace_between(h, "<!-- help:commands:start -->", "<!-- help:commands:end -->",
                        help_block(cmds), str(help_md))
    return {guide: g, help_md: h}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a target file would change")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    stale = []
    for path, new in render(root).items():
        old = path.read_text(encoding="utf-8")
        if old == new:
            continue
        stale.append(path)
        if args.check:
            rel = path.relative_to(root)
            diff = difflib.unified_diff(old.splitlines(), new.splitlines(),
                                        f"a/{rel}", f"b/{rel}", lineterm="", n=1)
            print("\n".join(list(diff)[:60]), file=sys.stderr)
        else:
            path.write_text(new, encoding="utf-8")
    if args.check and stale:
        names = ", ".join(str(p.relative_to(root)) for p in stale)
        print(f"gen-guide: stale generated blocks in {names}. "
              f"Run: python3 scripts/gen-guide.py", file=sys.stderr)
        return 1
    if not args.check:
        print(f"gen-guide: {'updated ' + str(len(stale)) + ' file(s)' if stale else 'up to date'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
