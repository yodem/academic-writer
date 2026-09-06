"""
footnote_backrefs.py - Remap intra-article footnote self-references.

Each writer unit (one entry in `data["sections"]`, the article-assembly
JSON fed to generate-docx.py) is drafted independently and numbers its own
footnotes starting from 1 in its own prose. When a unit's prose contains a
self-reference like "שוורץ (לעיל, הערה 6), עמ' 323" ("Schwartz, see note 6
above, p. 323"), the `6` is that unit's own LOCAL footnote ordinal -- the
6th footnote object that appears (in document order) among that unit's own
paragraphs.

Footnote *numbers* the reader actually sees in the final DOCX are assigned
implicitly, one at a time, by FootnoteAdder.add_footnote()
(lib/footnote_adder.py) as generate_docx() walks
data["sections"][*]["paragraphs"][*]["footnotes"][*] in document order. So
a unit's local footnote #6 might land as global footnote #14 once every
earlier unit's footnotes are counted -- and nothing updates the literal
text "הערה 6" inside that unit's own footnote/paragraph prose to say
"הערה 14".

This module fixes that: it walks `sections` once to build a per-section
local-ordinal -> global-ordinal map (matching exactly how generate_docx()
assigns global footnote numbers), then rewrites every genuine
"לעיל, הערה N" self-reference in that section's own paragraph/footnote text
to use the correct global ordinal.

Hard correctness constraint: only "לעיל, הערה N" (Hebrew "see note N
above") is a genuine intra-article self-reference and gets rewritten. A
bare "הערה N" that is NOT preceded by the literal token "לעיל" (e.g.
"עמ' 243, הערה 59", which refers to a CITED WORK's own footnote apparatus)
must never be touched.
"""

from __future__ import annotations

import copy
import re
import sys

# Matches "לעיל[,] הערה N" -- tolerates the comma being present or absent,
# and normal whitespace variation between "לעיל", "הערה" and the number.
# The literal "לעיל" token must be present immediately before "הערה N";
# this is what keeps a bare "הערה N" (a cited work's own footnote number)
# from ever matching.
_BACKREF_PATTERN = re.compile(r"לעיל\s*,?\s*הערה\s+(\d+)")


def _rewrite_text(text, local_to_global, section_index, unresolved):
    """Rewrite every `לעיל, הערה N` occurrence in `text` using
    `local_to_global` (that section's own local->global ordinal map).
    Occurrences whose N has no entry in the map are left byte-for-byte
    unchanged and recorded in `unresolved`.
    """
    if not text or "לעיל" not in text:
        return text

    def _replace(match):
        local_num = int(match.group(1))
        global_num = local_to_global.get(local_num)
        if global_num is None:
            unresolved.append(
                {
                    "section_index": section_index,
                    "local_ordinal": local_num,
                    "context": match.group(0),
                }
            )
            return match.group(0)
        # Preserve everything in the match up to the digits (the "לעיל...
        # הערה " prefix, comma/whitespace variations included), and swap
        # only the number itself.
        prefix = match.group(0)[: match.start(1) - match.start(0)]
        return prefix + str(global_num)

    return _BACKREF_PATTERN.sub(_replace, text)


def remap_backreferences(sections):
    """Rewrite `לעיל, הערה N` self-references from local to global footnote
    ordinals, section by section.

    Args:
        sections: the `data["sections"]` list (list of dicts with a
            "paragraphs" list -- see generate-docx.py / docx-generation.md
            for the schema). Not mutated; a deep copy is rewritten and
            returned.

    Returns:
        (rewritten_sections, unresolved) where `rewritten_sections` is a
        new list (deep copy of the input, with text fields rewritten) and
        `unresolved` is a list of dicts describing every `לעיל, הערה N`
        occurrence whose N did not resolve against its own section's local
        footnote count (malformed/hallucinated reference) -- left
        unchanged in the output text.
    """
    sections = copy.deepcopy(sections or [])

    # Pass 1: walk sections/paragraphs/footnotes in document order,
    # assigning each footnote object a local ordinal (resets per section)
    # and a global ordinal (running across the whole document) -- exactly
    # the order generate_docx() walks them, and exactly what
    # FootnoteAdder.add_footnote() will assign.
    global_ordinal = 0
    section_maps = []
    for sec in sections:
        local_ordinal = 0
        local_to_global = {}
        for para in sec.get("paragraphs", []) or []:
            if not isinstance(para, dict):
                continue
            for fn in para.get("footnotes", []) or []:
                if not isinstance(fn, dict):
                    continue
                local_ordinal += 1
                global_ordinal += 1
                local_to_global[local_ordinal] = global_ordinal
        section_maps.append(local_to_global)

    # Pass 2: rewrite each section's own paragraph/footnote text using
    # ONLY that section's own local->global map -- a unit's self-reference
    # is only ever to a footnote earlier in its own draft, never remapped
    # against another section's map.
    unresolved = []
    for section_index, (sec, local_to_global) in enumerate(zip(sections, section_maps)):
        paragraphs = sec.get("paragraphs", []) or []
        for i, para in enumerate(paragraphs):
            if isinstance(para, dict):
                if "text" in para:
                    para["text"] = _rewrite_text(
                        para["text"], local_to_global, section_index, unresolved
                    )
                for fn in para.get("footnotes", []) or []:
                    if isinstance(fn, dict) and "text" in fn:
                        fn["text"] = _rewrite_text(
                            fn["text"], local_to_global, section_index, unresolved
                        )
            elif isinstance(para, str):
                paragraphs[i] = _rewrite_text(
                    para, local_to_global, section_index, unresolved
                )

    return sections, unresolved


def warn_unresolved(unresolved, stream=None):
    """Print one warning line per unresolved back-reference to `stream`
    (defaults to sys.stderr). Non-fatal -- never raises, never stays
    silent.
    """
    if not unresolved:
        return
    stream = stream if stream is not None else sys.stderr
    for item in unresolved:
        print(
            "WARNING: unresolved footnote back-reference "
            f"{item['context']!r} in section {item['section_index']} "
            f"(local note {item['local_ordinal']} not found among that "
            "section's own footnotes)",
            file=stream,
        )
