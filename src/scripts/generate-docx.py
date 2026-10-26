#!/usr/bin/env python3
"""
Academic Writer — DOCX Generator

Generates a properly formatted .docx file from article JSON data.
Handles RTL (Hebrew) text correctly, with proper punctuation and citation formatting.

Uses the Hebrew Punctuation Rules reference to ensure typography is human-like, not AI-like.

Usage:
    python3 generate-docx.py --input article.json --output path.docx

Input JSON schema:
{
    "title": str,
    "thesis": str | null,
    "coverPage": {                       # optional; omit for no cover page
        "university": str | null,
        "faculty": str | null,
        "department": str | null,
        "title": str | null,             # falls back to top-level "title"
        "author": str | null,
        "studentId": str | null,
        "supervisor": str | null,
        "course": str | null,
        "date": str | null,              # caller supplies a formatted date
        "aiUseDeclaration": str | null    # defaults to DEFAULT_AI_USE_DECLARATION_HE/EN
    },
    "sections": [{
        "title": str,
        "paragraphs": [str | {"text": str, "footnotes": [...]}],
        "level": 1 | 2,                  # optional; 2 = Heading 2 (default 1)
        "subsections": [{"title": str, "paragraphs": [...]}],   # optional Heading 2s
        "kind": "bibliography"           # optional; also detected from the title
    }],
    "format": {
        "font": str,          # default: "David" (Hebrew and the document default)
        "latinFont": str,     # default: "Times New Roman" for Latin-dominant LTR
                              #   paragraphs (Hebrew words in them stay David);
                              #   null/"" turns the split off
        "bodySize": int,       # default: 11
        "titleSize": int,      # default: 16
        "headingSize": int,    # default: 13 (abstract headings, legacy headings)
        "heading1Size": int,   # default: 14 (Heading 1 style, bold)
        "heading2Size": int,   # default: 12 (Heading 2 style, bold)
        "headingStyles": bool, # default: true; false = plain bold paragraphs
        "showSectionTitles": bool,  # default: null = shown above 1500 words
        "sectionStartsNewPage": bool,  # default: true (pageBreakBefore on Heading 1)
        "toc": "auto" | bool,  # default: "auto" (see TOC_SECTION_THRESHOLD)
        "tocTitle": str,       # default: "תוכן העניינים" / "Contents"
        "noteDirection": "auto" | "document",  # default: "auto" (first strong char)
        "coverUnnumbered": bool,  # default: true (start=0, titlePg, empty first footer)
        "lineSpacing": float,  # default: 1.5
        "margins": float,      # default: 1.0 (inches)
        "isRtl": bool          # default: true
    },
    "totalWords": int
}

coverPage extra (layout only, all optional):
    "layout": "compact" (default) | "labeled"   # labeled = label line, then value line
    "labels": {"author": str, "supervisor": str, "course": str}  # caller-supplied
    "titleSize": int (18), "detailSize": int (14)               # labeled layout only
"""

import argparse
import json
import os
import re
import sys

from docx import Document
from docx.shared import Pt, Inches, Cm, Mm, Twips, RGBColor
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from footnote_adder import (  # noqa: E402
    FootnoteAdder,
    first_strong_direction,
    paragraph_fonts,
    split_rtl_segments,
)
from footnote_backrefs import remap_backreferences, warn_unresolved  # noqa: E402

TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "lib", "footnote_template.docx"
)


# --- Threshold for showing section titles ---
SECTION_TITLE_WORD_THRESHOLD = 1500

# --- Fonts (R-60) ---
# `format.font` (default David) is the Hebrew font and the document default.
# Paragraphs that are mostly Latin script (English bibliography entries,
# English footnotes, URL lines) use DEFAULT_LATIN_FONT. `format.latinFont`
# overrides it; a falsy value turns the split off.
DEFAULT_LATIN_FONT = "Times New Roman"

# --- Headings (R-62) ---
HEADING1_SIZE = 14
HEADING2_SIZE = 12

# --- Table of contents (R-55) ---
# `format.toc` = "auto" builds a TOC when the section headings are shown AND
# the article has a cover page or MORE THAN this many top-level sections.
TOC_SECTION_THRESHOLD = 3
TOC_INSTRUCTION = r' TOC \o "1-2" \h \z \u '

# Section titles that mark a bibliography even without `"kind": "bibliography"`.
BIBLIOGRAPHY_TITLES = frozenset({
    "ביבליוגרפיה", "רשימה ביבליוגרפית", "רשימת מקורות", "מקורות",
    "bibliography", "references", "works cited", "sources",
})


# --- Default AI-use disclosure text (cover page) ---
# Used when a caller supplies a `coverPage` object but omits
# `aiUseDeclaration`. Kept short, generic (no product names), and factual,
# per the researcher's institution's disclosure requirements. Reviewed and
# editable by a human -- do not bury this inline in the rendering code.
DEFAULT_AI_USE_DECLARATION_HE = (
    "בהכנת עבודה זו נעשה שימוש בכלי בינה מלאכותית לצורך מחקר, עריכה ו/או ניסוח, "
    "בהתאם לכללי הגילוי הנאות של המוסד האקדמי."
)
DEFAULT_AI_USE_DECLARATION_EN = (
    "AI tools were used in the preparation of this work for research, editing, "
    "and/or drafting assistance, in accordance with the academic institution's "
    "disclosure requirements."
)


def validate_hebrew_text(text: str) -> str:
    """
    Clean directional-mark and orphan-punctuation artefacts from article text.

    Fixes:
    - Unnecessary directional marks (RLM/LRM) -> removed
    - Orphan punctuation at paragraph start -> removed

    Deliberately NOT done here (author decisions 1 and 2, 2026-10-26):
    - The em dash is the correct Hebrew dash for an aside, so it is left
      untouched; it is no longer rewritten to a spaced hyphen.
    - Hebrew quotations keep the straight ASCII double quote; it is no longer
      rewritten to a gershayim. Gershayim stays only where the author typed it
      (abbreviations such as תנ״ך). Quote and dash typography is handled
      upstream (typography_fixes), never in this renderer.

    Args:
        text: Hebrew or mixed text string

    Returns:
        Text with stray directional marks removed; dashes and quotes unchanged
    """
    if not text:
        return text

    # Remove unnecessary directional marks that break rendering
    # DOCX handles bidirectionality automatically; manual marks cause issues

    # RLM (U+200F) before punctuation/closing brackets is usually wrong
    text = re.sub(r"\u200F+(?=[.,;:\)\]\"])", "", text)

    # LRM (U+200E) after opening parenthesis/bracket is usually wrong
    text = re.sub(r"(?<=[(\[])\u200E+", "", text)

    # Multiple consecutive directional marks should be removed
    text = re.sub(r"[\u200E\u200F]{2,}", "", text)

    # Orphan punctuation at paragraph start is removed
    if re.match(r"^\s*[.,;:]", text):
        # Remove the orphan punctuation
        text = re.sub(r"^\s*([.,;:])", "", text).strip()

    return text


_PPR_AFTER_BIDI = (
    "w:adjustRightInd",
    "w:snapToGrid",
    "w:spacing",
    "w:ind",
    "w:contextualSpacing",
    "w:mirrorIndents",
    "w:suppressOverlap",
    "w:jc",
    "w:textDirection",
    "w:textAlignment",
    "w:textboxTightWrap",
    "w:outlineLvl",
    "w:divId",
    "w:cnfStyle",
    "w:rPr",
    "w:sectPr",
    "w:pPrChange",
)


def _insert_bidi(pPr, rtl=True):
    """Insert ``w:bidi`` into a pPr (paragraph or style) in schema position."""
    if pPr.find(qn("w:bidi")) is not None:
        return
    bidi = OxmlElement("w:bidi")
    bidi.set(qn("w:val"), "1" if rtl else "0")
    pPr.insert_element_before(bidi, *_PPR_AFTER_BIDI)


def set_rtl_para(para, rtl=True):
    """Set paragraph direction via correctly ordered ``w:bidi``.

    ``rtl=False`` writes an explicit ``w:bidi w:val="0"`` (an LTR paragraph
    inside an RTL document, e.g. an English bibliography entry).

    OOXML requires ``w:bidi`` to precede spacing, indentation, and paragraph
    alignment (``w:jc``) inside ``w:pPr``. Appending it after the alignment is
    tolerated by some readers but causes Word for macOS to ignore the
    alignment on short RTL paragraphs such as headings.
    """
    _insert_bidi(para._p.get_or_add_pPr(), rtl)


def set_rtl_run(run):
    """Enable RTL on a specific run via w:rtl in rPr element."""
    rPr = run._element.get_or_add_rPr()
    rtl_elem = OxmlElement("w:rtl")
    rPr.append(rtl_elem)


def _set_fonts(rpr_fonts, ascii_font, cs_font):
    """Point every font slot explicitly. Word picks the slot by the run's
    ``w:rtl`` flag, not by the character (probed by rendering), so each run
    carries its own pair instead of relying on document-level slots."""
    for theme_attr in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
        if rpr_fonts.get(qn(theme_attr)) is not None:
            del rpr_fonts.attrib[qn(theme_attr)]
    rpr_fonts.set(qn("w:ascii"), ascii_font)
    rpr_fonts.set(qn("w:hAnsi"), ascii_font)
    rpr_fonts.set(qn("w:cs"), cs_font or ascii_font)


_RPR_ORDER = (
    "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike",
    "dstrike", "outline", "shadow", "emboss", "imprint", "noProof",
    "snapToGrid", "vanish", "webHidden", "color", "spacing", "w", "kern",
    "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd",
    "fitText", "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout",
    "specVanish", "oMath",
)


def _sort_rpr(rPr):
    """Put run-property children in schema order (CT_RPr is a sequence)."""
    def key(el):
        name = el.tag.rsplit("}", 1)[-1]
        return _RPR_ORDER.index(name) if name in _RPR_ORDER else len(_RPR_ORDER)

    children = sorted(list(rPr), key=key)
    for child in list(rPr):
        rPr.remove(child)
    for child in children:
        rPr.append(child)


def _style_run(run, font_name, font_size, bold, italic, is_rtl, cs_font=None):
    run.font.name = font_name
    if font_size is not None:
        run.font.size = Pt(font_size)
    run.bold = bold
    run.italic = italic
    _set_fonts(run._element.rPr.rFonts, font_name, cs_font or font_name)
    if is_rtl:
        # Complex-script formatting (bCs/iCs/szCs) is what Word reads for an
        # RTL run; w:b/w:sz alone leave Hebrew text unbolded / unsized.
        rPr = run._element.rPr
        if bold:
            rPr.append(OxmlElement("w:bCs"))
        if italic:
            rPr.append(OxmlElement("w:iCs"))
        if font_size is not None:
            szcs = OxmlElement("w:szCs")
            szcs.set(qn("w:val"), str(int(round(font_size * 2))))
            rPr.append(szcs)
        set_rtl_run(run)
        _sort_rpr(rPr)


# Sentence/clause-ending punctuation that must never sit BEFORE a footnote
# marker -- Hebrew academic convention (and this project's own house style)
# attaches the marker to the word it belongs to, immediately before any
# trailing comma/period/etc., not after it. A caller's `after` anchor can
# legitimately end in punctuation (e.g. copied verbatim from surrounding
# prose), so this is a deterministic normalization applied at the anchor
# boundary itself rather than relying on every caller to author `after`
# correctly. Measured on a real article: 38 markers landed after punctuation
# against 3 attached to the word, before this fix.
TRAILING_PUNCTUATION = ".,;:!?"


def _anchor_end_before_trailing_punctuation(text, idx, end):
    """Given a found anchor span text[idx:end], pull `end` back before any
    TRAILING_PUNCTUATION characters immediately preceding it -- so the
    footnote marker lands on the word side of the punctuation, never after
    it. Never shrinks the span to empty (a marker made of only punctuation
    is left as-is; there's no word to attach to).
    """
    trimmed_end = end
    while trimmed_end > idx and text[trimmed_end - 1] in TRAILING_PUNCTUATION:
        trimmed_end -= 1
    return trimmed_end if trimmed_end > idx else end


def add_para(
    doc,
    text,
    font_name,
    font_size,
    is_rtl=True,
    bold=False,
    italic=False,
    align=WD_ALIGN_PARAGRAPH.JUSTIFY,
    space_before=0,
    space_after=6,
    line_spacing=1.5,
    footnotes=None,
    footnote_adder=None,
    latin_font=None,
    auto_direction=False,
    style=None,
    page_break_before=None,
):
    """
    Add a paragraph with proper RTL handling for Hebrew text.

    Key principle: Write text naturally, let DOCX handle bidirectional rendering.
    No manual insertion of directional marks.

    Args:
        doc: python-docx Document
        text: Paragraph text (Hebrew or mixed)
        font_name: Font name (e.g., "David")
        font_size: Font size in points; None leaves the size to the style
        is_rtl: Whether text is right-to-left
        bold, italic: Text formatting; None leaves them to the style
        align: Paragraph alignment
        space_before, space_after: Spacing in points
        line_spacing: Line spacing multiplier (e.g., 1.5)
        latin_font: Font for a Latin-dominant LTR paragraph (None = off); its
            Hebrew words go in their own RTL runs and keep ``font_name``. An
            RTL paragraph keeps ``font_name`` for every character, Latin
            tokens included, so there is no font switch mid-sentence.
        auto_direction: In an RTL document, a paragraph whose first strong
            character is Latin becomes an LTR, left-aligned paragraph
            (w:bidi val=0, runs without w:rtl). Used for bibliography entries.
        style: Paragraph style name (e.g. "Heading 1")
        page_break_before: True/False writes w:pageBreakBefore; None inherits

    Returns:
        The Paragraph object
    """
    # Clean stray directional marks (dashes and quotes are left as typed)
    text = validate_hebrew_text(text)

    para_rtl = is_rtl
    if auto_direction and is_rtl and first_strong_direction(text) == "ltr":
        para_rtl = False
        align = WD_ALIGN_PARAGRAPH.LEFT
    ascii_font, cs_font = paragraph_fonts(text, font_name, latin_font, rtl=para_rtl)

    def add_text_runs(chunk):
        """Add ``chunk`` as one run, or, in an LTR paragraph that uses the
        Latin font, as separate runs so Hebrew words keep the Hebrew font
        (Word picks the font slot by the run's w:rtl flag, not by character)."""
        if not para_rtl and ascii_font != cs_font:
            for piece, piece_rtl in split_rtl_segments(chunk):
                run = para.add_run(piece)
                _style_run(
                    run, cs_font if piece_rtl else ascii_font, font_size, bold,
                    italic, piece_rtl, cs_font,
                )
        else:
            run = para.add_run(chunk)
            _style_run(run, ascii_font, font_size, bold, italic, para_rtl, cs_font)

    # Create paragraph
    para = doc.add_paragraph(style=style) if style else doc.add_paragraph()
    # In a <w:bidi/> paragraph Word renders jc="right" at the LEFT margin, so RTL
    # "right" alignment (headings, subtitles) is expressed as no jc: the bidi
    # default (start) is the right margin.
    para.alignment = None if (para_rtl and align == WD_ALIGN_PARAGRAPH.RIGHT) else align
    para.paragraph_format.space_before = Pt(space_before)
    para.paragraph_format.space_after = Pt(space_after)
    para.paragraph_format.line_spacing = line_spacing
    if page_break_before is not None:
        para.paragraph_format.page_break_before = page_break_before

    if para_rtl:
        set_rtl_para(para)
    elif is_rtl:
        set_rtl_para(para, rtl=False)

    if footnotes and footnote_adder:
        cursor = 0
        for fn in footnotes:
            marker = fn.get("after", "")
            fn_text = validate_hebrew_text(fn.get("text", ""))
            idx = text.find(marker, cursor) if marker else -1
            if idx < 0:
                continue
            end = _anchor_end_before_trailing_punctuation(text, idx, idx + len(marker))
            segment = text[cursor:end]
            if segment:
                add_text_runs(segment)
            footnote_adder.add_footnote(para, "", fn_text)
            cursor = end
        tail = text[cursor:]
        if tail:
            add_text_runs(tail)
    else:
        add_text_runs(text)

    return para


def add_page_numbers(doc):
    """Add centered page numbers in footer."""
    section = doc.sections[0]
    footer = section.footer
    para = footer.paragraphs[0]
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = para.add_run()
    fldChar1 = OxmlElement("w:fldChar")
    fldChar1.set(qn("w:fldCharType"), "begin")
    instrText = OxmlElement("w:instrText")
    instrText.text = "PAGE"
    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "end")
    run._r.append(fldChar1)
    run._r.append(instrText)
    run._r.append(fldChar2)


def configure_unnumbered_cover(doc):
    """Make the cover page unnumbered and the next page page 1 (R-63).

    Sets ``pgNumType start=0`` so the cover is page 0, enables ``titlePg`` and
    gives the first-page footer no PAGE field. Only meaningful when a cover
    page exists; without a cover, normal numbering from 1 is left alone.
    """
    section = doc.sections[0]
    sectPr = section._sectPr
    pg_num = sectPr.find(qn("w:pgNumType"))
    if pg_num is None:
        pg_num = OxmlElement("w:pgNumType")
        sectPr.insert_element_before(
            pg_num,
            "w:cols",
            "w:formProt",
            "w:vAlign",
            "w:noEndnote",
            "w:titlePg",
            "w:textDirection",
            "w:bidi",
            "w:rtlGutter",
            "w:docGrid",
            "w:printerSettings",
            "w:sectPrChange",
        )
    pg_num.set(qn("w:start"), "0")
    section.different_first_page_header_footer = True  # w:titlePg
    first_footer = section.first_page_footer
    first_footer.is_linked_to_previous = False  # creates the (empty) first-page footer


def _configure_styles(doc, font_name, body_size, is_rtl, h1_size, h2_size,
                      section_new_page, text_width_twips):
    """Document defaults, real Heading 1/2 styles and TOC 1/2 styles.

    - docDefaults: the document font in every slot and the body size, so text
      Word generates itself (TOC entries, footers) matches the body.
    - Heading 1: bold ``h1_size``, black, document font; ``pageBreakBefore``
      when ``section_new_page`` (R-59). Heading 2: bold ``h2_size``.
    - TOC 1 / TOC 2: document font, right dot-leader tab at the text width.
    """
    defaults = doc.styles.element.find(qn("w:docDefaults"))
    rpr = defaults.find(qn("w:rPrDefault")).find(qn("w:rPr"))
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    _set_fonts(rfonts, font_name, font_name)
    rfonts.set(qn("w:eastAsia"), font_name)
    for tag in ("w:sz", "w:szCs"):
        el = rpr.find(qn(tag))
        if el is None:
            el = OxmlElement(tag)
            rpr.append(el)
        el.set(qn("w:val"), str(int(round(body_size * 2))))
    _sort_rpr(rpr)

    for name, size in (("Heading 1", h1_size), ("Heading 2", h2_size)):
        style = doc.styles[name]
        style.font.bold = True
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0, 0, 0)
        style_rpr = style.element.get_or_add_rPr()
        sfonts = style_rpr.find(qn("w:rFonts"))
        if sfonts is None:
            sfonts = OxmlElement("w:rFonts")
            style_rpr.insert(0, sfonts)
        _set_fonts(sfonts, font_name, font_name)
        sfonts.set(qn("w:eastAsia"), font_name)
        for tag, val in (("w:bCs", None), ("w:szCs", str(int(round(size * 2))))):
            el = style_rpr.find(qn(tag))
            if el is None:
                el = OxmlElement(tag)
                style_rpr.append(el)
            if val is not None:
                el.set(qn("w:val"), val)
        _sort_rpr(style_rpr)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.space_before = Pt(12)
        style.paragraph_format.space_after = Pt(6)
        if name == "Heading 1":
            style.paragraph_format.page_break_before = True if section_new_page else None

    for level, indent_twips in ((1, 0), (2, 240)):
        style = doc.styles.add_style(f"toc {level}", WD_STYLE_TYPE.PARAGRAPH)
        style.style_id = f"TOC{level}"
        # A built-in style (Word rebuilds the TOC with it), not a custom one.
        style.element.attrib.pop(qn("w:customStyle"), None)
        style.base_style = doc.styles["Normal"]
        style.next_paragraph_style = doc.styles["Normal"]
        style.hidden = False
        style.priority = 39
        style.paragraph_format.space_after = Pt(5)
        style.paragraph_format.tab_stops.add_tab_stop(
            Twips(text_width_twips), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS
        )
        if indent_twips:
            style.paragraph_format.left_indent = Twips(indent_twips)
        if is_rtl:
            _insert_bidi(style.element.get_or_add_pPr(), True)


def _enable_update_fields(doc):
    """``w:updateFields`` makes Word refresh every field (the TOC) on open."""
    settings = doc.settings.element
    if settings.find(qn("w:updateFields")) is not None:
        return
    el = OxmlElement("w:updateFields")
    el.set(qn("w:val"), "true")
    anchor = None
    for tag in ("w:hdrShapeDefaults", "w:footnotePr", "w:endnotePr", "w:compat"):
        anchor = settings.find(qn(tag))
        if anchor is not None:
            break
    if anchor is not None:
        anchor.addprevious(el)
    else:
        settings.append(el)


def _field_run(para, kind=None, instr=None):
    run = para.add_run()
    if kind:
        fld = OxmlElement("w:fldChar")
        fld.set(qn("w:fldCharType"), kind)
        run._r.append(fld)
    if instr is not None:
        el = OxmlElement("w:instrText")
        el.set(qn("xml:space"), "preserve")
        el.text = instr
        run._r.append(el)
    return run


def add_toc(doc, entries, title_text, font_name, heading_size, body_size, is_rtl,
            latin_font, line_spacing):
    """Insert a real Word TOC field under a bold ``heading_size`` title (R-55).

    The field is ``TOC \\o "1-2" \\h \\z \\u``. Its cached result lists the
    headings WITHOUT page numbers: python-docx cannot paginate, so the page
    numbers are filled in by Word when the document is opened (the caller sets
    ``w:updateFields``). Until then, a viewer that does not update fields shows
    the titles only.

    ``entries`` is a list of ``(level, title)``; returns the paragraph list.
    """
    align = WD_ALIGN_PARAGRAPH.RIGHT if is_rtl else WD_ALIGN_PARAGRAPH.LEFT
    add_para(
        doc, title_text, font_name, heading_size, is_rtl=is_rtl, bold=True,
        align=align, space_before=0, space_after=12, line_spacing=line_spacing,
        latin_font=latin_font,
    )
    paragraphs = []
    last = len(entries) - 1
    for i, (level, text) in enumerate(entries):
        text = validate_hebrew_text(text)
        ascii_font, cs_font = paragraph_fonts(text, font_name, latin_font, rtl=is_rtl)
        para = doc.add_paragraph(style=f"toc {min(level, 2)}")
        if is_rtl:
            set_rtl_para(para)
        if i == 0:
            _field_run(para, "begin")
            _field_run(para, instr=TOC_INSTRUCTION)
            _field_run(para, "separate")
        run = para.add_run(text)
        _style_run(run, ascii_font, None, None, None, is_rtl, cs_font)
        if i == last:
            _field_run(para, "end")
        paragraphs.append(para)
    return paragraphs


def add_cover_page(
    doc,
    cover,
    font_name,
    body_size,
    title_size,
    heading_size,
    line_spacing,
    is_rtl,
    fallback_title,
    latin_font=None,
):
    """Render a cover page (שער) as the first page of the document.

    Renders whichever fields are present in `cover` (skipping None/missing/
    empty-string fields), then inserts a page break so the article title
    that follows always starts on a fresh page. Reuses `add_para` /
    `set_rtl_para` / `_style_run` -- the same styling path used everywhere
    else in this file -- rather than a parallel one.

    ``cover["layout"] == "labeled"`` is the venue-neutral layout refinement of
    R-54: bold title at ``titleSize`` (default 18), then for each of author /
    supervisor / course a LABEL line followed by a VALUE line, both at
    ``detailSize`` (default 14). Labels are caller-supplied in
    ``cover["labels"]`` (nothing is hard-coded); a field without a label
    renders as a value line only. The student ID joins the author value in
    parentheses. The default ("compact") layout is unchanged.
    """
    center = WD_ALIGN_PARAGRAPH.CENTER

    def render(text, font_size, bold=False, italic=False, space_before=0, space_after=6):
        if not text:
            return
        add_para(
            doc,
            text,
            font_name,
            font_size,
            is_rtl=is_rtl,
            bold=bold,
            italic=italic,
            align=center,
            space_before=space_before,
            space_after=space_after,
            line_spacing=line_spacing,
            latin_font=latin_font,
        )

    labeled = cover.get("layout") == "labeled"

    # Institutional header block: university / faculty / department.
    render(cover.get("university"), heading_size, bold=True, space_after=4)
    render(cover.get("faculty"), body_size, space_after=4)
    render(cover.get("department"), body_size, space_after=4)

    # Article title -- falls back to the top-level article title when the
    # cover page doesn't specify its own.
    cover_title = cover.get("title") or fallback_title
    if labeled:
        cover_title_size = cover.get("titleSize", 18)
    else:
        cover_title_size = title_size
    render(cover_title, cover_title_size, bold=True, space_before=36, space_after=24)

    if labeled:
        detail = cover.get("detailSize", 14)
        labels = cover.get("labels") or {}
        author = cover.get("author")
        student_id = cover.get("studentId")
        if author and student_id:
            author = f"{author} ({student_id})"
        elif student_id:
            author = student_id
        for key, value in (
            ("author", author),
            ("supervisor", cover.get("supervisor")),
            ("course", cover.get("course")),
        ):
            if not value:
                continue
            render(labels.get(key), detail, space_before=12, space_after=2)
            render(value, detail, space_after=4)
        render(cover.get("date"), detail, space_before=12, space_after=4)
    else:
        # Author / student ID / supervisor / course / date block.
        render(cover.get("author"), body_size, space_before=24, space_after=4)
        render(cover.get("studentId"), body_size, space_after=4)
        render(cover.get("supervisor"), body_size, space_after=4)
        render(cover.get("course"), body_size, space_after=4)
        render(cover.get("date"), body_size, space_after=4)

    # AI-use disclosure -- visually distinct (smaller, italic) from the
    # institutional/body text above; rendered last so it falls near the
    # bottom of the cover page in normal document flow.
    declaration = cover.get("aiUseDeclaration")
    if not declaration:
        declaration = DEFAULT_AI_USE_DECLARATION_HE if is_rtl else DEFAULT_AI_USE_DECLARATION_EN
    disclosure_size = max(8, body_size - 2)
    render(declaration, disclosure_size, italic=True, space_before=48, space_after=0)

    # Article body must never share a page with the cover content. The break
    # paragraph's run carries the document font like every other run.
    break_para = doc.add_page_break()
    break_run = break_para.runs[0]
    break_run.font.name = font_name
    _set_fonts(break_run._element.rPr.rFonts, font_name, font_name)


def _is_bibliography(section):
    """A section is a bibliography when it says so (``kind``) or is titled so."""
    if section.get("kind") == "bibliography" or section.get("bibliography") is True:
        return True
    title = re.sub(r"[\s:.־-]+$", "", (section.get("title") or "").strip()).lower()
    return title in BIBLIOGRAPHY_TITLES


def _flatten_sections(sections):
    """Expand ``subsections`` into following level-2 entries (one flat list)."""
    flat = []
    for sec in sections or []:
        entry = {k: v for k, v in sec.items() if k != "subsections"}
        entry["level"] = 2 if sec.get("level") == 2 else 1
        flat.append(entry)
        for sub in sec.get("subsections") or []:
            sub_entry = dict(sub)
            sub_entry["level"] = 2
            flat.append(sub_entry)
    return flat


def _merge_duplicate_titles(flat):
    """Merge consecutive top-level entries that carry the same title.

    ``aw docx`` emits one entry per writer unit (introduction, body,
    conclusion), repeating the section title; each section must start exactly
    one page and show its heading once (R-59). Runs after back-reference
    remapping, which needs the per-unit entries.
    """
    merged = []
    for entry in flat:
        prev = merged[-1] if merged else None
        title = (entry.get("title") or "").strip()
        if (
            prev is not None
            and entry["level"] == 1
            and prev["level"] == 1
            and title
            and title == (prev.get("title") or "").strip()
        ):
            prev["paragraphs"] = list(prev.get("paragraphs", [])) + list(
                entry.get("paragraphs", [])
            )
            continue
        merged.append(dict(entry))
    return merged


def generate_docx(data: dict, output_path: str):
    """Generate a .docx file from article data."""
    # Extract format settings with defaults
    fmt = data.get("format", {})
    font_name = fmt.get("font", "David")
    # Latin-dominant paragraphs (R-60); a falsy value, or the same font as
    # `font`, switches the split off.
    latin_font = fmt.get("latinFont", DEFAULT_LATIN_FONT) or None
    if latin_font == font_name:
        latin_font = None
    body_size = fmt.get("bodySize", 11)
    title_size = fmt.get("titleSize", 16)
    heading_size = fmt.get("headingSize", 13)
    heading_styles = fmt.get("headingStyles", True)
    h1_size = fmt.get("heading1Size", HEADING1_SIZE)
    h2_size = fmt.get("heading2Size", HEADING2_SIZE)
    section_new_page = fmt.get("sectionStartsNewPage", heading_styles)
    note_auto_direction = fmt.get("noteDirection", "auto") != "document"
    cover_unnumbered = fmt.get("coverUnnumbered", True)
    line_spacing = fmt.get("lineSpacing", 1.5)
    margin_value = fmt.get("margins", 1.0)
    # "in" preserves the historical default (margins was inches-only with no
    # unit field, and every existing caller's numbers assume inches).
    margins_unit = fmt.get("marginsUnit", "in")
    margin_length = Cm(margin_value) if margins_unit == "cm" else Inches(margin_value)
    is_rtl = fmt.get("isRtl", True)
    # python-docx's bundled template defaults to US Letter (215.9mm x
    # 279.4mm); every Israeli academic document is A4. "A4" is the default
    # here rather than inheriting the template's Letter size.
    page_size = fmt.get("pageSize", "A4")

    total_words = data.get("totalWords", 0)
    show_override = fmt.get("showSectionTitles")
    if show_override is None:
        show_section_titles = total_words > SECTION_TITLE_WORD_THRESHOLD
    else:
        show_section_titles = bool(show_override)

    title = data.get("title", "Untitled")
    thesis = data.get("thesis", None)

    # Expand sub-sections, then rewrite intra-article footnote self-references
    # ("לעיל, הערה N") from each writer unit's own LOCAL footnote ordinal to
    # the document-wide GLOBAL ordinal FootnoteAdder is about to assign below.
    # Must run before the section/paragraph loop that calls add_para, and
    # before duplicate-title entries are merged (they are per-unit).
    sections = _flatten_sections(data.get("sections", []))
    sections, unresolved_backrefs = remap_backreferences(sections)
    warn_unresolved(unresolved_backrefs)
    if heading_styles:
        sections = _merge_duplicate_titles(sections)

    cover_page = data.get("coverPage")

    # Headings that will actually render (they feed the TOC)
    toc_entries = []
    if heading_styles and show_section_titles:
        toc_entries = [
            (sec["level"], sec.get("title", ""))
            for sec in sections
            if (sec.get("title") or "").strip()
        ]
    toc_opt = fmt.get("toc", "auto")
    top_level_count = sum(1 for level, _ in toc_entries if level == 1)
    if toc_opt in (True, "true", "on", "yes"):
        want_toc = True
    elif toc_opt in (False, "false", "off", "no"):
        want_toc = False
    else:  # "auto": a cover page, or more than TOC_SECTION_THRESHOLD sections
        want_toc = bool(cover_page) or top_level_count > TOC_SECTION_THRESHOLD
    want_toc = want_toc and bool(toc_entries)
    toc_title = fmt.get("tocTitle") or ("תוכן העניינים" if is_rtl else "Contents")

    doc = Document(TEMPLATE_PATH)
    doc._body.clear_content()
    footnote_adder = FootnoteAdder(
        is_rtl=is_rtl,
        font_name=font_name,
        latin_font=latin_font,
        auto_direction=note_auto_direction,
    )

    # Set page size and margins
    for section in doc.sections:
        if page_size == "A4":
            section.page_width = Mm(210)
            section.page_height = Mm(297)
        elif page_size == "Letter":
            section.page_width = Inches(8.5)
            section.page_height = Inches(11)
        # else: leave the template's own page size untouched (an
        # unrecognized value is not silently coerced to a guess).
        section.top_margin = margin_length
        section.bottom_margin = margin_length
        section.left_margin = margin_length
        section.right_margin = margin_length

    first_section = doc.sections[0]
    text_width_twips = int(
        (first_section.page_width - first_section.left_margin - first_section.right_margin)
        / 635
    )
    _configure_styles(
        doc, font_name, body_size, is_rtl, h1_size, h2_size,
        section_new_page and heading_styles, text_width_twips,
    )

    def toc_block():
        add_toc(
            doc, toc_entries, toc_title, font_name, h1_size, body_size, is_rtl,
            latin_font, line_spacing,
        )
        _enable_update_fields(doc)

    # Cover page (שער) -- optional, additive. Renders first, before the
    # article title, and always ends with a page break so the article body
    # never shares a page with cover content.
    if cover_page:
        add_cover_page(
            doc,
            cover_page,
            font_name,
            body_size,
            title_size,
            heading_size,
            line_spacing,
            is_rtl,
            title,
            latin_font=latin_font,
        )

    # With a cover, the TOC gets its own page right after it (page 1 when the
    # cover is unnumbered); the article title then starts a new page.
    title_page_break = None
    if want_toc and cover_page:
        toc_block()
        title_page_break = True

    # Title (bold, centered)
    title_align = WD_ALIGN_PARAGRAPH.CENTER
    add_para(
        doc,
        title,
        font_name,
        title_size,
        is_rtl=is_rtl,
        bold=True,
        align=title_align,
        space_after=6,
        line_spacing=line_spacing,
        latin_font=latin_font,
        page_break_before=title_page_break,
    )

    # Thesis subtitle (italic, centered) - always shown if present
    if thesis:
        add_para(
            doc,
            thesis,
            font_name,
            body_size,
            is_rtl=is_rtl,
            italic=True,
            align=title_align,
            space_after=12,
            line_spacing=line_spacing,
            latin_font=latin_font,
        )

    # Abstract(s)
    abstract_rendered = False
    abstract_data = data.get("abstract", None)
    if abstract_data:
        primary_abstract = abstract_data.get("primary", None)
        secondary_abstract = abstract_data.get("secondary", None)

        if primary_abstract:
            abstract_rendered = True
            # Abstract heading
            abstract_heading = "תקציר" if is_rtl else "Abstract"
            add_para(
                doc,
                abstract_heading,
                font_name,
                heading_size,
                is_rtl=is_rtl,
                bold=True,
                align=(WD_ALIGN_PARAGRAPH.RIGHT if is_rtl else WD_ALIGN_PARAGRAPH.LEFT),
                space_before=12,
                space_after=6,
                line_spacing=line_spacing,
                latin_font=latin_font,
            )
            # Abstract body
            add_para(
                doc,
                primary_abstract,
                font_name,
                body_size,
                is_rtl=is_rtl,
                align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                space_after=6,
                line_spacing=line_spacing,
                latin_font=latin_font,
            )

        if secondary_abstract:
            abstract_rendered = True
            # Secondary abstract (e.g., English abstract for Hebrew article)
            secondary_is_rtl = not is_rtl  # opposite direction
            add_para(
                doc,
                "Abstract",
                font_name,
                heading_size,
                is_rtl=secondary_is_rtl,
                bold=True,
                align=(
                    WD_ALIGN_PARAGRAPH.RIGHT
                    if secondary_is_rtl
                    else WD_ALIGN_PARAGRAPH.LEFT
                ),
                space_before=12,
                space_after=6,
                line_spacing=line_spacing,
                latin_font=latin_font,
            )
            add_para(
                doc,
                secondary_abstract,
                font_name,
                body_size,
                is_rtl=secondary_is_rtl,
                align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                space_after=12,
                line_spacing=line_spacing,
                latin_font=latin_font,
            )

    # Without a cover the TOC follows the front matter, before the sections.
    toc_before_sections = False
    if want_toc and not cover_page:
        toc_block()
        toc_before_sections = True

    # The first top-level heading starts a new page only when real front matter
    # (an abstract, or the TOC) precedes it on the page; the title/thesis block
    # alone does not count, so no title-only page is produced.
    first_heading_breaks = abstract_rendered or toc_before_sections
    first_h1_done = False

    # Body sections
    for sec in sections:
        sec_title = sec.get("title", "")
        level = sec["level"]
        # Conditional section titles (an empty title never renders a heading)
        if show_section_titles and (sec_title or "").strip():
            heading_align = (
                WD_ALIGN_PARAGRAPH.RIGHT if is_rtl else WD_ALIGN_PARAGRAPH.LEFT
            )
            if heading_styles:
                heading = add_para(
                    doc,
                    sec_title,
                    font_name,
                    None,
                    is_rtl=is_rtl,
                    bold=None,
                    align=heading_align,
                    space_before=12,
                    space_after=6,
                    line_spacing=line_spacing,
                    latin_font=latin_font,
                    style=f"Heading {level}",
                )
                if level == 1 and not first_h1_done and not first_heading_breaks:
                    heading.paragraph_format.page_break_before = False
            else:
                add_para(
                    doc,
                    sec_title,
                    font_name,
                    heading_size,
                    is_rtl=is_rtl,
                    bold=True,
                    align=heading_align,
                    space_before=12,
                    space_after=6,
                    line_spacing=line_spacing,
                    latin_font=latin_font,
                    page_break_before=(
                        True
                        if (section_new_page and level == 1
                            and (first_h1_done or first_heading_breaks))
                        else None
                    ),
                )
            if level == 1:
                first_h1_done = True

        bibliography = _is_bibliography(sec)

        # Section paragraphs
        for para_item in sec.get("paragraphs", []):
            if isinstance(para_item, dict):
                p_text = para_item.get("text", "")
                p_fns = para_item.get("footnotes", [])
            else:
                p_text = para_item
                p_fns = []
            add_para(
                doc,
                p_text,
                font_name,
                body_size,
                is_rtl=is_rtl,
                align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                space_after=6,
                line_spacing=line_spacing,
                footnotes=p_fns,
                footnote_adder=footnote_adder,
                latin_font=latin_font,
                auto_direction=bibliography and note_auto_direction,
            )

    if cover_page and cover_unnumbered:
        configure_unnumbered_cover(doc)
    add_page_numbers(doc)
    doc.save(output_path)
    footnote_adder.finalize_footnotes(output_path)
    print(f"Saved: {output_path}")
    print(f"Words: {total_words}")
    print(f"Sections: {len(sections)}")
    print(
        f"Section titles: {'shown' if show_section_titles else 'hidden (under ' + str(SECTION_TITLE_WORD_THRESHOLD) + ' words)'}"
    )
    print(
        "TOC: "
        + (
            "real Word field, titles only; page numbers appear after Word's "
            "update-fields prompt is accepted on open"
            if want_toc
            else "none"
        )
    )


def main():
    parser = argparse.ArgumentParser(description="Generate academic article DOCX")
    parser.add_argument("--input", required=True, help="Path to article JSON file")
    parser.add_argument("--output", required=True, help="Output .docx path")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    generate_docx(data, args.output)


if __name__ == "__main__":
    main()
