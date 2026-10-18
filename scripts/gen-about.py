#!/usr/bin/env python3
"""Generate the dashboard's About data from features.json and the skills' frontmatter.

Sources of truth:
  - features.json                      (features, subfeatures, status, `tested`, optional name_he/description_he)
  - src/skills/*/SKILL.md frontmatter  (description, metadata.summary, user-invocable), joined by each feature's `sources`
  - manifests/academic-writer.json     (version)

Target:
  - src/scripts/courses/dashboard/about.json

Usage:
  python3 scripts/gen-about.py            # rewrite in place (idempotent)
  python3 scripts/gen-about.py --check    # exit 1 if the output would change
  python3 scripts/gen-about.py --root DIR # operate on another checkout (used by tests)

Standard library only. No model call: a feature's text comes from its skill's summary, else from the
`description_he` written next to it in features.json.
"""
from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

OUT = "src/scripts/courses/dashboard/about.json"
GUIDE = "/academic-writer:intro"
TESTED = ("e2e", "unit", "manual", "not tested yet")

# Short first steps by role, plain words, at most five each. Hebrew first; the guide has the detail.
ONBOARDING: Dict[str, List[str]] = {
    "student": [
        "הריצו /academic-writer:setup ובחרו תיקיית בית: שם יישמרו הפרופיל והסמסטר שלכם.",
        "הריצו /academic-writer:courses כדי להגדיר את הסמסטר ואת הקורסים.",
        "פתחו את הלוח עם /academic-writer:dashboard וראו את השבוע שלפניכם.",
        "הוסיפו מאמר או ספר לספרייה עם /academic-writer:ingest.",
        "התחילו לכתוב עם /academic-writer:write; כל שלב ייראה בלשונית כתיבה.",
    ],
    "lecturer": [
        "הריצו /academic-writer:setup ובחרו תיקיית בית ותפקיד מרצה.",
        "הריצו /academic-writer:init בתיקיית הפרויקט כדי לתת לו פרופיל.",
        "הוסיפו מאמרים קודמים כדי שהתוסף ילמד את הסגנון שלכם.",
        "כתבו מאמר חדש עם /academic-writer:write, או הגיהו קיים עם /academic-writer:proofread.",
    ],
    "researcher": [
        "הריצו /academic-writer:setup ובחרו תיקיית בית ותפקיד חוקר.",
        "הריצו /academic-writer:init בתיקיית המחקר כדי לתת לה פרופיל.",
        "הוסיפו מקורות לספרייה עם /academic-writer:ingest או /academic-writer:ingest-book.",
        "נסחו שאלת מחקר עם /academic-writer:ideate וכתבו עם /academic-writer:write.",
        "פתחו את הלוח עם /academic-writer:dashboard כדי לעקוב אחרי הכתיבה.",
    ],
}


def _load_guide(root: Path):
    """Reuse gen-guide.py's frontmatter reader (one parser for both generators)."""
    path = Path(__file__).resolve().parent / "gen-guide.py"
    spec = importlib.util.spec_from_file_location("gen_guide", path)
    if spec is None or spec.loader is None:
        raise SystemExit("gen-about: cannot load gen-guide.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("gen_guide", mod)
    spec.loader.exec_module(mod)
    return mod


def skill_for(root: Path, guide, sources: List[str]) -> Optional[Tuple[str, Dict[str, Any]]]:
    """First source that is a src/skills/<name>/SKILL.md file: (name, frontmatter)."""
    for src in sources:
        m = re.fullmatch(r"src/skills/([^/]+)/SKILL\.md", src)
        if not m:
            continue
        path = root / src
        if path.is_file():
            fm = guide.parse_frontmatter(path.read_text(encoding="utf-8"))
            return str(fm.get("name") or m.group(1)), fm
    return None


def build_sub(node: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": node["id"], "name": node.get("name_he") or node.get("name") or node["id"],
            "status": node.get("status"), "tested": node.get("tested"),
            "subfeatures": [build_sub(s) for s in node.get("subfeatures") or []]}


def build_feature(root: Path, guide, node: Dict[str, Any]) -> Dict[str, Any]:
    skill = skill_for(root, guide, node.get("sources") or [])
    command = None
    description = node.get("description_he") or node.get("name") or node["id"]
    if skill:
        name, fm = skill
        summary = guide.summary_for(fm)
        if summary:
            description = summary
        if fm.get("user-invocable"):
            command = guide.PREFIX + name
    subs = [build_sub(sub) for sub in node.get("subfeatures") or []]
    return {"id": node["id"], "name_he": node.get("name_he") or node.get("name") or node["id"],
            "description_he": description, "command": command, "status": node.get("status"),
            "tested": node.get("tested"), "subfeatures": subs}


def render(root: Path) -> str:
    guide = _load_guide(root)
    try:
        version = json.loads((root / "manifests/academic-writer.json").read_text(encoding="utf-8"))["version"]
        features = json.loads((root / "features.json").read_text(encoding="utf-8"))["features"]
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit("gen-about: cannot read inputs: %s" % exc)
    about = {"version": version,
             "features": [build_feature(root, guide, f) for f in features],
             "onboarding": ONBOARDING, "guide": GUIDE}
    return json.dumps(about, ensure_ascii=False, indent=2) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Generate the dashboard About data.")
    ap.add_argument("--check", action="store_true", help="exit 1 if the output would change")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    target = root / OUT
    new = render(root)
    old = target.read_text(encoding="utf-8") if target.is_file() else ""
    if old == new:
        if not args.check:
            print("gen-about: up to date")
        return 0
    if args.check:
        diff = difflib.unified_diff(old.splitlines(), new.splitlines(), "a/" + OUT, "b/" + OUT, lineterm="", n=1)
        print("\n".join(list(diff)[:60]), file=sys.stderr)
        print("gen-about: stale %s. Run: python3 scripts/gen-about.py" % OUT, file=sys.stderr)
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new, encoding="utf-8")
    print("gen-about: updated %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
