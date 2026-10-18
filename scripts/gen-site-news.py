#!/usr/bin/env python3
"""Generate the "What's new" block of the product site from CHANGELOG.md.

Rewrites the text between `<!-- news:start -->` and `<!-- news:end -->` in site/index.html with the
last three released versions (the `[Unreleased]` section is skipped): version, date, and up to five
short bullets taken from the Added and then the Fixed lists.

Usage:
  python3 scripts/gen-site-news.py            # rewrite in place (idempotent)
  python3 scripts/gen-site-news.py --check    # exit 1 if the block is stale
  python3 scripts/gen-site-news.py --root DIR # operate on another checkout

Standard library only; no model call.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

RELEASES = 3
MAX_BULLETS = 5
MAX_CHARS = 110
START, END = "<!-- news:start -->", "<!-- news:end -->"
HEADING = re.compile(r"^## \[(\d+\.\d+\.\d+)\]\s*[—-]\s*(\d{4}-\d{2}-\d{2})\s*$")


def parse_changelog(text: str) -> list[dict]:
    """Released versions, newest first: {version, date, added: [...], fixed: [...]} (raw bullet text)."""
    releases: list[dict] = []
    cur = None
    section = None
    for line in text.splitlines():
        if line.startswith("## "):
            m = HEADING.match(line)
            cur = {"version": m.group(1), "date": m.group(2), "added": [], "fixed": []} if m else None
            if cur:
                releases.append(cur)
            section = None
        elif cur is not None and line.startswith("### "):
            name = line[4:].strip().lower()
            section = name if name in ("added", "fixed") else None
        elif cur is not None and section and line.startswith("- "):
            cur[section].append(line[2:].strip())
    return releases


def short(bullet: str) -> str:
    """One short plain-text line: the bold lead when there is one, else the first sentence."""
    m = re.match(r"\*\*(.+?)\*\*", bullet)
    text = m.group(1) if m else bullet
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = text.replace("**", "").replace("`", "")
    if not m:
        text = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    text = re.sub(r"\s+", " ", text).strip().rstrip(".:;,")
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rsplit(" ", 1)[0].rstrip(".,;:—-") + "…"
    return text


def render(releases: list[dict]) -> str:
    out = ['<div class="news__grid">']
    for rel in releases[:RELEASES]:
        bullets = [short(b) for b in rel["added"] + rel["fixed"]][:MAX_BULLETS]
        out.append('  <article class="news__rel rv">')
        out.append(f'    <h3 dir="ltr"><span class="news__ver">v{rel["version"]}</span> '
                   f'<time class="news__date" datetime="{rel["date"]}">{rel["date"]}</time></h3>')
        out.append('    <ul dir="ltr">')
        out.extend(f"      <li>{html.escape(b, quote=False)}</li>" for b in bullets)
        out.append("    </ul>")
        out.append("  </article>")
    out.append("</div>")
    return "\n".join(out)


def build(root: Path) -> tuple[Path, str, str]:
    index = root / "site" / "index.html"
    old = index.read_text(encoding="utf-8")
    releases = parse_changelog((root / "CHANGELOG.md").read_text(encoding="utf-8"))
    if not releases:
        raise SystemExit("gen-site-news: no released version found in CHANGELOG.md")
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(old):
        raise SystemExit(f"gen-site-news: {index} has no {START} ... {END} block")
    new = pattern.sub(lambda _: f"{START}\n{render(releases)}\n{END}", old, count=1)
    return index, old, new


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if the block is stale")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    args = ap.parse_args(argv)
    index, old, new = build(Path(args.root))
    if old == new:
        print("gen-site-news: up to date")
        return 0
    if args.check:
        print("gen-site-news: site/index.html news block is stale; run python3 scripts/gen-site-news.py", file=sys.stderr)
        return 1
    index.write_text(new, encoding="utf-8")
    print("gen-site-news: updated site/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
