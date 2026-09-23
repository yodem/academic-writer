#!/usr/bin/env python3
"""Score proofread corrections that were actually applied in the output text.

Each expected item carries a `context` (a snippet containing the error exactly once in the
fixture) and `fixed` (that snippet after the correction). An item counts as recalled when
`fixed` occurs in the proofed text. Anchoring on context, not on a global search for
`before`, keeps the score correct when `before` is a substring of `after` or when the same
word is legitimately correct elsewhere.

`protected` lists strings that must survive verbatim (quotations, correct occurrences of a
word that is wrong elsewhere, the first allowed use of a capped connective). Each one that
is missing counts as a change applied where it must not be.

Exit 1 when any class is under its `min_recall`, or when any protected string was altered.
"""
import json
import sys
import unicodedata
from pathlib import Path


def _norm(text):
    return unicodedata.normalize("NFC", text)


def score(proofed_text, expected):
    text = _norm(proofed_text)
    hits, totals = {}, {}
    for item in expected.get("items", []):
        kind = item["class"]
        totals[kind] = totals.get(kind, 0) + 1
        if "fixed" in item:
            hit = _norm(item["fixed"]) in text
        else:  # legacy item without context: after present and before absent
            hit = _norm(item["after"]) in text and _norm(item["before"]) not in text
        hits[kind] = hits.get(kind, 0) + int(hit)
    recall = {kind: hits.get(kind, 0) / total for kind, total in totals.items()}
    altered = sum(1 for keep in expected.get("protected", []) if _norm(keep) not in text)
    return {"by_class": recall, "inside_quote_applied": altered}


def main(argv):
    if len(argv) != 2:
        print("usage: applied_recall.py <proofed.md> <expected.json>", file=sys.stderr)
        return 2
    expected = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    result = score(Path(argv[0]).read_text(encoding="utf-8"), expected)
    print(json.dumps(result, ensure_ascii=False))
    under = any(result["by_class"].get(k, 0.0) < v for k, v in expected.get("min_recall", {}).items())
    return int(under or result["inside_quote_applied"] > 0)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
