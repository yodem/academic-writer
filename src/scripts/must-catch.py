#!/usr/bin/env python3
"""Emit deterministic term and style corrections, plus optional hspell flags."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def scan(text, styles, terms):
    lines = text.splitlines()
    changes = []

    def add(kind, before, after, line):
        changes.append({"id": "mc-%04d" % (len(changes) + 1), "class": kind, "before": before,
                        "after": after, "line": line, "finder": "must-catch", "meaningRisk": "low", "mustCatch": True})

    for item in terms.get("canon", []):
        for variant in item.get("variants", []):
            for index, line in enumerate(lines, 1):
                for match in re.finditer(re.escape(variant), line):
                    add("names_terms", match.group(), item["form"], index)

    for item in styles.get("banned", []):
        for index, line in enumerate(lines, 1):
            for match in re.finditer(re.escape(item["word"]), line):
                add("style_words", match.group(), item.get("replacement"), index)
    for word in styles.get("filler", []):
        for index, line in enumerate(lines, 1):
            for match in re.finditer(re.escape(word), line):
                add("style_words", match.group(), None, index)

    for item in styles.get("capped", []):
        count_by_unit = {}
        for index, line in enumerate(lines, 1):
            if item["maxPer"] == "chapter" and line.startswith("#"):
                count_by_unit.clear()
            if item["maxPer"] == "paragraph" and not line.strip():
                count_by_unit.clear()
                continue
            for match in re.finditer(re.escape(item["word"]), line):
                count_by_unit["count"] = count_by_unit.get("count", 0) + 1
                if count_by_unit["count"] > item["max"]:
                    # Occurrences beyond the cap take the configured alternative, if any.
                    add("style_words", match.group(), item.get("replacement"), index)
    return changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--style-words", required=True)
    parser.add_argument("--terms", required=True)
    parser.add_argument("--hspell", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    text = Path(args.text).read_text(encoding="utf-8")
    styles = json.loads(Path(args.style_words).read_text(encoding="utf-8"))
    terms = json.loads(Path(args.terms).read_text(encoding="utf-8"))
    changes = scan(text, styles, terms)
    if args.hspell:
        script = Path(__file__).with_name("spellcheck-candidates.py")
        result = subprocess.run([sys.executable, str(script), "--input", args.text], capture_output=True, text=True)
        if result.returncode:
            print(result.stderr, file=sys.stderr)
            return result.returncode
        candidates = json.loads(result.stdout).get("candidates", [])
        for candidate in candidates:
            changes.append({"id": "mc-%04d" % (len(changes) + 1), "class": "typo", "before": candidate["token"],
                            "after": None, "line": candidate["line"], "finder": "must-catch", "meaningRisk": "low",
                            "mustCatch": True, "status": "flag"})
    print(json.dumps({"changes": changes}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
