#!/usr/bin/env python3
"""Read, check, set or bump the plugin version across every registered location.

One deterministic implementation, used by the release workflow, the pre-commit hook
and tests/test_version_consistency.py — so "where does the version live" is answered
in exactly one place (scripts/version-locations.json) and never re-derived.

    version-sync.py --show
    version-sync.py --check                 # exit 1 on drift, print the table
    version-sync.py --fix                   # write every location to the canonical value
    version-sync.py --set 0.7.0
    version-sync.py --bump minor            # major | minor | patch
    version-sync.py --level-from-message "feat: thing"   # print the implied bump level
    version-sync.py --level-since-tag       # highest level across commits since the last release tag

Every write preserves the file's existing indentation and trailing newline.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / "scripts" / "version-locations.json"
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def load_registry() -> dict:
    with REGISTRY.open(encoding="utf-8") as fh:
        return json.load(fh)


def _read_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _detect_indent(text: str) -> int:
    m = re.search(r"\n(\s+)\S", text)
    if not m:
        return 2
    first = m.group(1)
    return len(first.expandtabs(2))


def _get(doc, path):
    node = doc
    for key in path:
        node = node[key]
    return node


def _set(doc, path, value):
    node = doc
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


def read_all(reg: dict) -> list[tuple[str, list, str | None, str | None]]:
    """Return (file, path, value, error) for every registered location."""
    rows = []
    for loc in reg["locations"]:
        path = REPO / loc["file"]
        try:
            rows.append((loc["file"], loc["path"], str(_get(_read_json(path), loc["path"])), None))
        except FileNotFoundError:
            rows.append((loc["file"], loc["path"], None, "file not found"))
        except (KeyError, IndexError, TypeError):
            rows.append((loc["file"], loc["path"], None, "path not present"))
        except json.JSONDecodeError as exc:
            rows.append((loc["file"], loc["path"], None, f"invalid JSON: {exc}"))
    return rows


def canonical_version(reg: dict) -> str:
    c = reg["canonical"]
    return str(_get(_read_json(REPO / c["file"]), c["path"]))


def write_version(reg: dict, version: str) -> list[str]:
    """Write `version` to every registered location. Returns the files changed."""
    if not SEMVER_RE.match(version):
        raise SystemExit(f"version-sync: '{version}' is not MAJOR.MINOR.PATCH")
    by_file: dict[str, list[list]] = {}
    for loc in reg["locations"]:
        by_file.setdefault(loc["file"], []).append(loc["path"])
    changed = []
    for rel, paths in by_file.items():
        path = REPO / rel
        text = path.read_text(encoding="utf-8")
        doc = json.loads(text)
        before = json.dumps(doc, sort_keys=True)
        for p in paths:
            _set(doc, p, version)
        if json.dumps(doc, sort_keys=True) == before:
            continue
        indent = _detect_indent(text)
        out = json.dumps(doc, indent=indent, ensure_ascii=False)
        path.write_text(out + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
        changed.append(rel)
    return changed


def bump(version: str, level: str) -> str:
    m = SEMVER_RE.match(version)
    if not m:
        raise SystemExit(f"version-sync: current version '{version}' is not semver")
    major, minor, patch = (int(g) for g in m.groups())
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    if level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise SystemExit(f"version-sync: unknown bump level '{level}'")


LEVEL_RANK = {"patch": 0, "minor": 1, "major": 2}


def level_from_message(msg: str) -> str:
    """Conventional-commit bump level. Breaking beats feature beats everything else."""
    first = msg.strip().splitlines()[0] if msg.strip() else ""
    if re.match(r"^[a-z]+(\([^)]*\))?!:", first) or re.search(r"^BREAKING[ -]CHANGE", msg, re.M):
        return "major"
    if re.match(r"^feat(\([^)]*\))?:", first):
        return "minor"
    return "patch"


def level_from_messages(messages) -> str:
    """Highest level implied by ANY message in the push.

    A push carries many commits and GitHub's `head_commit` is only the last one, so
    inferring from it alone ships a patch for a merge commit that contains features.
    """
    best = "patch"
    for msg in messages:
        lvl = level_from_message(msg or "")
        if LEVEL_RANK[lvl] > LEVEL_RANK[best]:
            best = lvl
    return best


TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def _run_git(args: list[str], repo: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return result.stdout


def latest_release_tag(repo: Path = REPO) -> str | None:
    """The newest `v<semver>` tag reachable from HEAD, ordered by version — not
    lexically (so v0.6.10 sorts after v0.6.9, unlike a plain string sort).

    Only tags that are actual ancestors of HEAD count: a tag cut on some other
    branch must not be mistaken for "the last release this history shipped".
    Returns None when no such tag exists, so the caller can fall back to
    considering the whole history.
    """
    raw = _run_git(["tag", "--list", "v*"], repo)
    candidates: list[tuple[tuple[int, int, int], str]] = []
    for tag in raw.split():
        m = TAG_RE.match(tag)
        if not m:
            continue
        check = subprocess.run(
            ["git", "merge-base", "--is-ancestor", tag, "HEAD"],
            cwd=repo, capture_output=True,
        )
        if check.returncode == 0:
            candidates.append((tuple(int(g) for g in m.groups()), tag))
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1][1]


def commit_messages_since(tag: str | None, repo: Path = REPO) -> list[str]:
    """Full subject+body of every commit after `tag` up to HEAD (or all of HEAD's
    history when `tag` is None — the no-tags-yet case).

    Uses a NUL byte to separate whole commit messages, since a message body can
    contain blank lines and can't be split on those.
    """
    range_arg = f"{tag}..HEAD" if tag else "HEAD"
    try:
        raw = _run_git(["log", range_arg, "--format=%B%x00"], repo)
    except subprocess.CalledProcessError:
        # No commits at all yet (e.g. a brand-new repo) — HEAD doesn't resolve.
        return []
    return [part.strip() for part in raw.split("\x00") if part.strip()]


def level_since_tag(repo: Path = REPO) -> str:
    """The highest conventional-commit level across every commit since the last
    release tag (or the whole history when there is no tag yet).

    This is the fix for the failed-release regression: a bump level derived from
    a single push is lost forever when that push's release job fails before a
    tag is cut. Deriving it from tag..HEAD means a `feat:` from a failed push is
    still counted once a later, unrelated `fix:` push finally succeeds.
    """
    tag = latest_release_tag(repo)
    msgs = commit_messages_since(tag, repo)
    if not msgs:
        return "patch"
    return level_from_messages(msgs)


def messages_from_event(path: Path) -> list[str]:
    """Extract commit messages from a GitHub push-event payload (or a bare JSON array).

    Accepts the whole `github.event` object, its `commits` array, or a list of strings —
    so the workflow can hand over `toJSON(github.event)` without reshaping it.
    """
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    if isinstance(payload, dict):
        commits = payload.get("commits") or []
        msgs = [c.get("message", "") for c in commits if isinstance(c, dict)]
        head = payload.get("head_commit")
        if isinstance(head, dict) and head.get("message"):
            msgs.append(head["message"])
        return msgs
    if isinstance(payload, list):
        return [c.get("message", "") if isinstance(c, dict) else str(c) for c in payload]
    return []


CHANGELOG = "CHANGELOG.md"
UNRELEASED_RE = re.compile(r"^## \[Unreleased\]\s*$", re.M)


def release_changelog(version: str, today: str) -> str:
    """Rename `## [Unreleased]` to `## [version] — date` and open a fresh Unreleased above it.

    Finding 10 of the 2026-09-01 improvements page was that [Unreleased] had accumulated
    already-shipped features. It accumulates because nothing ever renamed it: the release
    workflow bumped manifests and published, and the CHANGELOG was left to a human who
    reasonably forgot. Doing it in the same step that writes the version is the fix.

    Idempotent by construction: a second call finds the new [Unreleased] section empty and
    leaves the file alone, so a re-run cannot emit an empty version heading.
    """
    path = REPO / CHANGELOG
    if not path.exists():
        return "no CHANGELOG.md — nothing to do"
    text = path.read_text(encoding="utf-8")
    m = UNRELEASED_RE.search(text)
    if not m:
        return "no '## [Unreleased]' heading — nothing to do"
    if f"## [{version}]" in text:
        return f"[{version}] already present — nothing to do"

    after = text[m.end():]
    nxt = re.search(r"^## \[", after, re.M)
    body = (after[: nxt.start()] if nxt else after).strip()
    if not body:
        return "[Unreleased] is empty — not creating an empty version heading"

    replacement = f"## [Unreleased]\n\n## [{version}] — {today}"
    path.write_text(text[: m.start()] + replacement + text[m.end():], encoding="utf-8")
    return f"[Unreleased] -> [{version}] — {today}, fresh [Unreleased] opened"


def print_table(rows, expected: str) -> bool:
    width = max(len(f"{f} {'.'.join(str(x) for x in p)}") for f, p, _, _ in rows)
    ok = True
    for rel, path, value, error in rows:
        label = f"{rel} {'.'.join(str(x) for x in path)}"
        if error:
            print(f"  {label:<{width}}  ERROR: {error}")
            ok = False
        elif value != expected:
            print(f"  {label:<{width}}  {value}   <-- DRIFT (expected {expected})")
            ok = False
        else:
            print(f"  {label:<{width}}  {value}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--show", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--fix", action="store_true")
    g.add_argument("--set", metavar="X.Y.Z")
    g.add_argument("--bump", choices=("major", "minor", "patch"))
    g.add_argument("--release-changelog", metavar="X.Y.Z",
                   help="Rename ## [Unreleased] to ## [X.Y.Z] — <today> and open a fresh one")
    ap.add_argument("--today", metavar="YYYY-MM-DD", default=None,
                    help="Date for --release-changelog (default: UTC today). Explicit so a test is reproducible.")
    g.add_argument("--level-from-message", metavar="MSG")
    g.add_argument("--level-from-event", metavar="EVENT_JSON",
                   help="GitHub push-event payload file; uses the highest level across ALL its commits")
    g.add_argument("--show-last-tag", action="store_true",
                   help="Print the release tag --level-since-tag measures from (or NONE)")
    g.add_argument("--level-since-tag", action="store_true",
                   help="Highest level across every commit since the last v<semver> release "
                        "tag reachable from HEAD (or all history if there is no tag yet). Use "
                        "this instead of --level-from-event: a push-scoped level is lost when "
                        "that push's release job fails before a tag is cut.")
    args = ap.parse_args()

    if args.release_changelog is not None:
        from datetime import datetime, timezone

        today = args.today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        print("version-sync: " + release_changelog(args.release_changelog, today))
        return 0

    if args.level_from_message is not None:
        print(level_from_message(args.level_from_message))
        return 0

    if args.level_from_event is not None:
        msgs = messages_from_event(Path(args.level_from_event))
        if not msgs:
            print("patch")
            return 0
        print(level_from_messages(msgs))
        return 0

    if args.show_last_tag:
        print(latest_release_tag() or "NONE")
        return 0

    if args.level_since_tag:
        print(level_since_tag())
        return 0

    reg = load_registry()

    if args.bump or args.set or args.fix:
        if args.fix:
            target = canonical_version(reg)
        elif args.set:
            target = args.set
        else:
            target = bump(canonical_version(reg), args.bump)
        changed = write_version(reg, target)
        print(f"version-sync: set {target} across {len(reg['locations'])} location(s)")
        for c in changed:
            print(f"  wrote {c}")
        print(target)
        return 0

    expected = canonical_version(reg)
    rows = read_all(reg)
    if args.show:
        print_table(rows, expected)
        return 0

    print(f"version-sync: canonical = {expected} ({reg['canonical']['file']})")
    ok = print_table(rows, expected)
    if ok:
        print(f"version-sync: all {len(rows)} location(s) agree")
        return 0
    print(
        "\nversion-sync: DRIFT. Run `python3 scripts/version-sync.py --fix` to write the\n"
        "canonical value everywhere, then re-run `npm run build` so the built plugin.json\n"
        "matches, and commit both.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
