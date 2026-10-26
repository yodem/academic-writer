#!/usr/bin/env python3
"""Emit deterministic term and style corrections, plus optional hspell flags.

Matches are whole words: Hebrew attaches prefixes (ו ה ב כ ל מ ש) and suffixes to a
word, so a raw substring match on a stem corrupts its inflected forms (a replaced
stem inside a longer word, a non-word in the output). A match therefore counts only
when no letter follows it and, before it, there is either no letter or a cluster of
one to three prefix letters standing at a word start. Quoted source text, footnote
definitions, the bibliography, code, URLs and frontmatter are never touched: a
source's spelling is kept as printed."""
import argparse
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

HEB_LETTER = re.compile("[\u05d0-\u05ea]")
# Letters plus niqqud and cantillation marks, geresh/gershayim inside a word, and Latin/digits.
WORD_CHAR = re.compile("[\u0591-\u05c7\u05d0-\u05ea\u05f0-\u05f4A-Za-z0-9]")
PREFIX_LETTERS = set("והבכלמש")
MAX_AMBIGUOUS = 10  # ambiguous quote marks per paragraph read every way; beyond that, protect conservatively
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
TABLE_DELIM = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")
HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.*\S)\s*$")
FOOTNOTE_DEF = re.compile(r"^\s*\[\^[^\]]+\]:")
BLOCKQUOTE = re.compile(r"^ {0,3}>")
SETEXT = re.compile(r"^ {0,3}(=+|-+)\s*$")
BIBLIOGRAPHY_TITLES = {"ביבליוגרפיה", "רשימה ביבליוגרפית", "רשימת מקורות", "רשימת המקורות", "מקורות",
                       "מקורות ראשוניים", "מקורות משניים", "bibliography", "references", "works cited", "sources"}
PROTECTED_INLINE = re.compile(r'(?<!`)(`+)(?!`)[\s\S]*?(?<!`)\1(?!`)|(?:https?|ftp)://[^\s"\u201c\u201d\u05f4<>]+|www\.[^\s"\u201c\u201d\u05f4<>]+|\]\([^)\n]*\)')


def _is_word_char(ch):
    """A letter, digit or combining mark of any script, or a Hebrew geresh/gershayim."""
    return bool(ch) and (ch.isalnum() or unicodedata.category(ch).startswith("M") or WORD_CHAR.match(ch) is not None)


def _open_end(word):
    """A phrase rule that ends in a space ("חשוב לציין כי ") or in a bare prefix
    ("מן הראוי לציין ש") is meant to run into the next word."""
    last = word.split(" ")[-1]
    return word.endswith((" ", "\t")) or (" " in word and 0 < len(last) <= 3 and set(last) <= PREFIX_LETTERS)


def _boundary(line, start, end, word):
    """None when line[start:end] is not a whole word; else the prefix cluster (possibly
    empty) that stands before it. A cluster of one to three prefix letters at a word
    start is allowed, since Hebrew attaches ו ה ב כ ל מ ש to the word."""
    after = line[end:end + 1]
    if not _open_end(word):
        if _is_word_char(after):
            return None
        if after in ('"', "'") and HEB_LETTER.match(line[end + 1:end + 2] or " "):
            return None  # acronym or geresh continues the word (רמב"ם, ג'וק)
    if word[:1].isspace():
        return ""
    i = start
    while i > 0 and HEB_LETTER.match(line[i - 1]):
        i -= 1
    cluster = line[i:start]
    if not cluster:
        return "" if not (start and _is_word_char(line[start - 1])) else None
    if not HEB_LETTER.match(line[start]) or len(cluster) > 3 or not set(cluster) <= PREFIX_LETTERS:
        return None
    return cluster if not (i and _is_word_char(line[i - 1])) else None


def _mark_kind(line, i):
    """'word' for a double quote inside a word (רמב"ם, תשכ"ב, הרמב"מיים), 'quote' for a
    quotation mark, 'either' when both readings fit: a quotation glued to a prefix
    cluster (ה"יש מאין", וב"תשורי") reads the same as an acronym on a prefix-like
    stem (המו"לים, שו"תים)."""
    prev, nxt = line[i - 1:i], line[i + 1:i + 2]
    if not (prev and HEB_LETTER.match(prev) and nxt and HEB_LETTER.match(nxt)):
        return "quote"
    j = i
    while j > 0 and HEB_LETTER.match(line[j - 1]):
        j -= 1
    cluster = line[j:i]
    glued_prefix = len(cluster) <= 3 and set(cluster) <= PREFIX_LETTERS and not _is_word_char(line[j - 1:j])
    longer_word = HEB_LETTER.match(line[i + 2:i + 3] or " ") is not None
    return "either" if glued_prefix and longer_word else "word"


def _quote_spans(text, carry=None):
    """Spans inside quotation marks over a whole paragraph (a quotation may run
    across lines): curly “…” (nested), older ״…״ and straight "…". A double quote
    inside a word (רמב"ם, תשכ"ב, הרמב"מיים) is not a quotation mark. An unmatched
    opener protects the rest of the paragraph and the whole next paragraph (a
    quotation may run across paragraphs; carrying it only one paragraph keeps a stray
    mark from switching off corrections for the rest of the article): `carry` maps each mark still open
    when the paragraph starts (mark -> open depth), and those still open at its end are returned."""
    carry = carry or {}
    inline = [(m.start(), m.end()) for m in PROTECTED_INLINE.finditer(text)]

    def in_inline(i):
        return any(a <= i < b for a, b in inline)

    spans = list(inline)
    still_open = {}
    stack = [-1] * carry.get("\u201c", 0)
    for i, ch in enumerate(text):
        if in_inline(i):
            continue
        if ch == "\u201c":
            stack.append(i)
        elif ch == "\u201d" and stack:
            start = stack.pop()
            spans.append((max(start, 0), i + 1))
    if stack:
        spans += [(max(s, 0), len(text)) for s in stack]
        opened_here = sum(1 for s in stack if s >= 0)
        if opened_here:
            still_open["\u201c"] = opened_here  # nesting depth opened in this paragraph
    for mark in ('"', "\u05f4"):
        kinds = [(i, _mark_kind(text, i)) for i, ch in enumerate(text) if ch == mark and not in_inline(i)]
        sure = [i for i, kind in kinds if kind == "quote"]
        either = [i for i, kind in kinds if kind == "either"]
        head = [-1] if carry.get(mark) else []
        # Protect what ANY reading puts inside quotation marks: each ambiguous mark read as
        # an acronym and as a quotation mark, in every combination. Missing a fix is cheap
        # (the proofreader proposes it); rewriting quoted source text is not.
        if len(either) > MAX_AMBIGUOUS:
            readings = [head + sorted(sure + either)]
            spans.append((min(either), len(text)))
            still_open[mark] = 1
        else:
            readings = [head + sorted(sure + [m for bit, m in enumerate(either) if mask >> bit & 1])
                        for mask in range(1 << len(either))]
        for marks in readings:
            for a, b in zip(marks[0::2], marks[1::2]):
                spans.append((max(a, 0), b + 1))
            if len(marks) % 2:
                spans.append((max(marks[-1], 0), len(text)))
                if marks[-1] >= 0:
                    still_open[mark] = 1  # a possible opener carries into the next paragraph
    return spans, still_open


def _fence(line):
    m = FENCE.match(line)
    return (m.group(1)[0], len(m.group(1))) if m else None


def _table_rows(lines):
    """Indices of GFM table lines: a header row, its delimiter row and the body rows,
    with or without outer pipes."""
    rows = set()
    for i, line in enumerate(lines):
        if not TABLE_DELIM.match(line) or i == 0 or "|" not in lines[i - 1]:
            continue
        rows.update((i - 1, i))
        j = i + 1
        while j < len(lines) and lines[j].strip() and "|" in lines[j]:
            rows.add(j)
            j += 1
    return rows


def _scannable_lines(text):
    """Yield (line_no, line, protected_spans, kind) for lines whose prose may be changed;
    kind is "text", "heading" or "blank". A skipped heading (a bibliography title) is
    yielded with an empty line so that caps still reset at it.
    Quotation spans are computed per paragraph and mapped back onto its lines."""
    lines = text.splitlines()
    tables = _table_rows(lines)
    keep = []
    in_front = bool(lines) and lines[0].strip() == "---"
    fence = None
    bib_level = None
    in_note = False
    in_blockquote = False  # a quoted block: its ">" lines and their lazy continuation lines
    setext_titles = set()
    heading_lines = set()  # every line classified as a heading in the first pass
    for index, line in enumerate(lines):
        if in_front:
            if index > 0 and line.strip() in ("---", "..."):
                in_front = False
            keep.append(False)
            continue
        f = _fence(line)
        if fence is not None:
            if f and f[0] == fence[0] and f[1] >= fence[1] and not line.strip()[f[1]:].strip():
                fence = None
            keep.append(False)
            continue
        if f:
            fence = f
            keep.append(False)
            continue
        m = HEADING.match(line)
        quoted_or_note = (BLOCKQUOTE.match(line) or FOOTNOTE_DEF.match(line)
                          or (line.strip() and (in_blockquote or (in_note and (line[:1].isspace() or lines[index - 1].strip())))))
        setext = (not m and not quoted_or_note and line.strip() and index + 1 < len(lines)
                  and SETEXT.match(lines[index + 1]) and not HEADING.match(lines[index + 1]))
        if index > 0 and SETEXT.match(line) and index - 1 in setext_titles:
            keep.append(False)  # the underline of a Setext heading
            continue
        if m or setext:
            heading_lines.add(index)
            if setext:
                setext_titles.add(index)
            in_note = False
            in_blockquote = False
            level = len(m.group(1)) if m else (1 if lines[index + 1].strip()[0] == "=" else 2)
            title = re.sub(r"[*_`#:]+", "", m.group(2) if m else line).strip().lower()
            if bib_level is not None and level <= bib_level:
                bib_level = None
            if title in BIBLIOGRAPHY_TITLES:
                bib_level = level
            keep.append(bib_level is None)
            continue
        if BLOCKQUOTE.match(line):
            in_blockquote = True
        elif not line.strip():
            in_blockquote = False
        if FOOTNOTE_DEF.match(line):
            in_note = True
        elif in_note and line.strip() and not line[:1].isspace() and not lines[index - 1].strip():
            in_note = False  # a non-indented paragraph after a blank line ends the note
        keep.append(not (bib_level is not None or in_note or in_blockquote or line.lstrip().startswith("|")
                         or index in tables))
    # A paragraph is a run of kept, non-blank lines that are not headings; a heading
    # or a blank line stands alone. Skipped lines never get a yield.
    def para_line(n):
        return keep[n] and lines[n].strip() and n not in heading_lines

    index = 0
    carry = {}
    while index < len(lines):
        if not para_line(index):
            if keep[index] and lines[index].strip():
                # a heading stands alone and does not continue or close a quotation
                yield index + 1, lines[index], _quote_spans(lines[index])[0], "heading"
            elif keep[index]:
                yield index + 1, lines[index], [], "blank"
            elif index in heading_lines:
                yield index + 1, "", [], "heading"  # a skipped heading still ends a chapter
            index += 1
            continue
        end = index
        while end < len(lines) and para_line(end):
            end += 1
        spans, carry = _quote_spans("\n".join(lines[index:end]), carry)
        offset = 0
        for n in range(index, end):
            length = len(lines[n])
            local = [(max(a, offset) - offset, min(b, offset + length) - offset) for a, b in spans
                     if a < offset + length and b > offset]
            yield n + 1, lines[n], local, "text"
            offset += length + 1
        index = end


def _matches(word, line, protected):
    """(match, occurrence, prefixed) for each whole-word, unprotected match of `word`.
    The occurrence is the match's 1-based position among ALL raw occurrences of the
    word on the line, the index apply-changes.py resolves by. `prefixed` is True when
    the match stands after a prefix cluster: מממש may be מ+ממש or the verb מממש, so
    such a match is reported for the author instead of applied."""
    for occurrence, match in enumerate(re.finditer(re.escape(word), line), 1):
        if any(a < match.end() and match.start() < b for a, b in protected):  # any overlap
            continue
        cluster = _boundary(line, match.start(), match.end(), word)
        if cluster is None:
            continue
        # A rule ending in a bare prefix ("…לציין ש") glued to the next word is a guess too:
        # in "לציין שינוי" the ש belongs to שינוי.
        glued_end = not word.endswith((" ", "\t")) and _open_end(word) and _is_word_char(line[match.end():match.end() + 1])
        yield match, occurrence, bool(cluster) or glued_end


def scan(text, styles, terms):
    # apply-changes.py resolves `before` on NFC-normalized text, so match on the same form.
    text = unicodedata.normalize("NFC", text)
    lines = list(_scannable_lines(text))
    changes = []

    def add(kind, before, after, line, occurrence=None, prefixed=False):
        change = {"id": "mc-%04d" % (len(changes) + 1), "class": kind, "before": before,
                  "after": after, "line": line, "finder": "must-catch", "meaningRisk": "low", "mustCatch": True}
        if prefixed:
            # The prefix reading is a guess (מממש, מבני), so the author confirms it.
            change.update({"meaningRisk": "medium", "mustCatch": False, "prefixed": True})
        if occurrence is not None:
            # Nth (1-based) occurrence of `before` on this line. Set only when the
            # same line can carry more than one instance of the flagged span (the
            # capped-word rule below): apply-changes.py needs it to disambiguate
            # which instance to touch instead of reporting skipReason="ambiguous-match".
            change["occurrence"] = occurrence
        changes.append(change)

    def add_all(kind, word, after):
        word = unicodedata.normalize("NFC", word)
        for index, line, protected, _kind in lines:
            raw = line.count(word)
            for match, occurrence, prefixed in _matches(word, line, protected):
                add(kind, match.group(), after, index, occurrence if raw > 1 else None, prefixed)

    for item in terms.get("canon", []):
        for variant in item.get("variants", []):
            if variant:
                add_all("names_terms", variant, item["form"])

    for item in styles.get("banned", []):
        add_all("style_words", item["word"], item.get("replacement"))
    for word in styles.get("filler", []):
        add_all("style_words", word, None)

    for item in styles.get("capped", []):
        count_by_unit = {}
        previous = 0
        for index, line, protected, kind in lines:
            if item["maxPer"] == "paragraph" and index > previous + 1:
                count_by_unit.clear()  # a blank or skipped line between them ends the paragraph
            previous = index
            if kind == "heading" or (item["maxPer"] == "paragraph" and kind == "blank"):
                count_by_unit.clear()  # a heading ends a chapter and a paragraph; a blank line a paragraph
            if kind == "blank":
                continue
            for match, line_occurrence, prefixed in _matches(unicodedata.normalize("NFC", item["word"]), line, protected):
                if prefixed:
                    continue  # מממש may not be the capped word at all; never count or rewrite a guess
                count_by_unit["count"] = count_by_unit.get("count", 0) + 1
                if count_by_unit["count"] > item["max"]:
                    # Occurrences beyond the cap take the configured alternative, if any.
                    # line_occurrence is this match's 1-based position among ALL
                    # occurrences of the word on THIS line (not the cross-line cap
                    # count), so a downstream applier can target exactly this one
                    # even when an earlier, still-allowed occurrence shares the line.
                    add("style_words", match.group(), item.get("replacement"), index, occurrence=line_occurrence)
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
