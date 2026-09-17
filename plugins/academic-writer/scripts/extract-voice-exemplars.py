#!/usr/bin/env python3
"""
Academic Writer — Voice Exemplar Extraction

Picks a few real body paragraphs from the researcher's finished academic
articles and writes them to `.academic-helper/voice-exemplars.md`, where the
Gemini MCP server's calibration bundle shows them to Gemini as few-shot voice
examples.

Why this exists (2026-09-15 prompt review): Gemini received a 2,200-word
description of the author's voice and a JSON style fingerprint, but never a
single paragraph of the author's actual prose, and the researcher judged its
output "not academic, not my voice". Surface counts do not explain that
judgement: on paragraph length, sentence length, first-person and hedging
rates, Gemini's output (111 / 23.6 / 0.9 / 1.4) already sits inside the range
of the author's own academic papers (97-134 / 23.5-25.5 / 0.8-1.5 / 1.0-2.0).
What was missing is the thing a description cannot carry, the voice itself,
and showing real paragraphs is the most reliable way to steer a model toward
it.

Choose the inputs. The selection cannot tell a finished paper from a course
reflection. On a real past-articles/ folder, the whole-folder run picked a
colloquial course reflection as an exemplar, while pointing the script at the
author's best-graded paper produced four properly academic paragraphs. Pass
the article(s) that best represent the researcher's finished academic writing.

Selection is deterministic (same inputs -> same exemplars), stdlib only:
  1. Split each input into paragraphs; keep body paragraphs within
     thresholds.json > voice.exemplars word bounds, with at least two
     sentences, at least one parenthetical source citation, and mostly
     letters of the target language. Identical paragraphs (after Unicode and
     whitespace normalization) count once.
  2. Prefer paragraphs where a quotation is followed by the author's own words
     (the analytic move a section-writer paragraph needs), then paragraphs
     closest to the median length, then input order.
  3. At most maxPerFile per input file when several files are given, so no
     single paper dominates; a single chosen file may supply all `count`.

Usage:
  python3 extract-voice-exemplars.py past-articles/best-paper.docx [more ...] \
      --output .academic-helper/voice-exemplars.md [--language hebrew]
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import unicodedata
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from style_text_extraction import read_corpus  # noqa: E402

_QUOTE_THEN_WORDS_RE = re.compile("[\"\\u05F4\\u201C\\u201D][^\"\\u05F4\\u201C\\u201D]{3,}[\"\\u05F4\\u201C\\u201D][^.?!]*?\\s\\S+\\s\\S+")
_SENTENCE_END_RE = re.compile(r"[.?!](?:\s|$)")
# A parenthetical that points at a source: a number, a page/chapter marker
# (עמ׳ / פרק / שם), or "ibid". Required, because a paragraph that cites nothing
# is usually a personal reflection or a course note.
_CITATION_RE = re.compile("\\([^()]*(?:\\d|\\u05E2\\u05DE['\\u05F3]|\\u05E4\\u05E8\\u05E7|\\u05E9\\u05DD|ibid|p\\.|pp\\.)[^()]*\\)")
_HEBREW_RE = re.compile("[\\u0590-\\u05FF]")
_LATIN_RE = re.compile(r"[A-Za-z]")
# Invisible characters that differ between two copies of the same paragraph
# (bidi marks, no-break space, zero-width characters) and defeat exact dedup.
_INVISIBLE_RE = re.compile("[\\u200B-\\u200F\\u202A-\\u202E\\u2066-\\u2069\\u00A0\\uFEFF]")


def _load_thresholds(script_dir: Path) -> dict:
    for candidate in (script_dir.parent / "thresholds.json", script_dir.parent.parent / "thresholds.json"):
        if candidate.is_file():
            data = json.loads(candidate.read_text(encoding="utf-8"))
            return data.get("voice", {}).get("exemplars", {})
    return {}


def _paragraphs(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _dedup_key(paragraph: str) -> str:
    return re.sub(r"\s+", " ", _INVISIBLE_RE.sub(" ", unicodedata.normalize("NFC", paragraph))).strip()


def _is_language(paragraph: str, language: str) -> bool:
    heb = len(_HEBREW_RE.findall(paragraph))
    lat = len(_LATIN_RE.findall(paragraph))
    if language == "hebrew":
        return heb > 0 and heb >= lat
    return lat > heb


def select_exemplars(texts: dict[str, str], language: str, count: int, min_words: int, max_words: int, max_per_file: int) -> list[dict]:
    candidates = []
    seen: set[str] = set()
    for order, (name, text) in enumerate(texts.items()):
        for paragraph in _paragraphs(text):
            words = len(paragraph.split())
            if words < min_words or words > max_words:
                continue
            if len(_SENTENCE_END_RE.findall(paragraph)) < 2:
                continue
            if not _is_language(paragraph, language):
                continue
            if not _CITATION_RE.search(paragraph):
                continue
            key = _dedup_key(paragraph)
            if key in seen:
                continue
            seen.add(key)
            candidates.append({"file": name, "order": order, "text": paragraph, "words": words})
    if not candidates:
        return []
    median = statistics.median(c["words"] for c in candidates)
    for c in candidates:
        c["analysis_after_quote"] = bool(_QUOTE_THEN_WORDS_RE.search(c["text"]))
        c["distance"] = abs(c["words"] - median)

    def rank(c: dict) -> tuple:
        return (not c["analysis_after_quote"], c["distance"], c["order"], c["text"])

    limit = count if len(texts) == 1 else max_per_file
    per_file: dict[str, list[dict]] = {}
    for c in sorted(candidates, key=rank):
        bucket = per_file.setdefault(c["file"], [])
        if len(bucket) < limit:
            bucket.append(c)
    pooled = sorted((c for bucket in per_file.values() for c in bucket), key=rank)
    return pooled[:count]


def render(exemplars: list[dict]) -> str:
    header = [
        "# Voice exemplars",
        "<!-- Generated by scripts/extract-voice-exemplars.py. Real paragraphs by the author, shown to Gemini as voice examples. Edit freely; separate paragraphs with a line containing only --- . -->",
        "",
    ]
    return "\n".join(header) + "\n---\n".join(e["text"] + "\n" for e in exemplars)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Extract real voice exemplar paragraphs from the researcher's finished articles.")
    parser.add_argument("inputs", nargs="+", help="article file(s) or folder(s); pass the researcher's finished academic papers")
    parser.add_argument("--output", help="where to write voice-exemplars.md (default: print to stdout)")
    parser.add_argument("--language", default="hebrew", help="hebrew or english (default: hebrew)")
    args = parser.parse_args(argv)

    cfg = _load_thresholds(Path(__file__).resolve().parent)
    missing = [k for k in ("count", "minWords", "maxWords", "maxPerFile") if not isinstance(cfg.get(k), int)]
    if missing:
        print(json.dumps({"error": "thresholds.json voice.exemplars missing keys: " + ", ".join(missing)}), file=sys.stderr)
        return 2

    texts: dict[str, str] = {}
    warnings: list[str] = []
    for item in args.inputs:
        found, warns = read_corpus(Path(item))
        texts.update(found)
        warnings.extend(warns)

    exemplars = select_exemplars(texts, args.language.lower(), cfg["count"], cfg["minWords"], cfg["maxWords"], cfg["maxPerFile"])
    if not exemplars:
        print(json.dumps({"exemplars": 0, "warnings": warnings + ["no paragraph met the exemplar criteria"]}, ensure_ascii=False))
        return 1

    content = render(exemplars)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
    else:
        sys.stdout.write(content)
    summary = {
        "exemplars": len(exemplars),
        "output": args.output,
        "picked": [{"file": e["file"], "words": e["words"], "analysis_after_quote": e["analysis_after_quote"]} for e in exemplars],
        "warnings": warnings,
    }
    print(json.dumps(summary, ensure_ascii=False), file=sys.stdout if args.output else sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
