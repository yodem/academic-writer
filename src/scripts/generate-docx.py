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
    "sections": [{"title": str, "paragraphs": [str]}],
    "format": {
        "font": str,          # default: "David"
        "bodySize": int,       # default: 11
        "titleSize": int,      # default: 16
        "headingSize": int,    # default: 13
        "lineSpacing": float,  # default: 1.5
        "margins": float,      # default: 1.0 (inches)
        "isRtl": bool          # default: true
    },
    "totalWords": int
}
"""

import argparse
import json
import os
import re
import sys

from docx import Document
from docx.shared import Pt, Inches, Cm, Mm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from footnote_adder import FootnoteAdder  # noqa: E402
from footnote_backrefs import remap_backreferences, warn_unresolved  # noqa: E402

TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "lib", "footnote_template.docx"
)


# --- Threshold for showing section titles ---
SECTION_TITLE_WORD_THRESHOLD = 1500


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
    Fix common Hebrew typographic errors that betray AI origin.

    Fixes:
    - Em-dashes (—) → replaced with space-hyphen-space
    - Straight quotes (") → replaced with gereshayim (״)
    - Unnecessary directional marks (RLM/LRM) → removed

    Args:
        text: Hebrew or mixed text string

    Returns:
        Cleaned text with AI typography tells removed
    """
    if not text:
        return text

    # 1. Replace em-dashes with space-hyphen-space
    # Em-dashes are a signature AI pattern; humans don't use them in Hebrew
    text = re.sub(r"[—\u2014]", " - ", text)

    # 2. Replace straight quotes with gereshayim (Hebrew quotation marks)
    # English straight quotes are wrong in Hebrew academic writing
    #
    # Hebrew academic prose also uses a straight quote MID-WORD as a
    # rashei-tevot / acronym marker (e.g. תנ"ך, מל"א, לפנה"ס) -- a single,
    # unpaired quote with a Hebrew letter immediately on both sides. If those
    # are left in the pool for the pair-matching regex below, an acronym's
    # lone quote gets greedily paired with the START of the next unrelated
    # real quotation, corrupting the pairing for every quote that follows in
    # the paragraph (root cause of the "mismatched quotes" defect). Convert
    # acronym-style quotes to gershayim individually FIRST so they can never
    # participate in pair-matching.
    text = re.sub(r'(?<=[א-ת])"(?=[א-ת])', "״", text)
    text = re.sub(r'"([^"]{0,200})"', r"״\1״", text)

    # 3. Remove unnecessary directional marks that break rendering
    # DOCX handles bidirectionality automatically; manual marks cause issues

    # RLM (U+200F) before punctuation/closing brackets is usually wrong
    text = re.sub(r"\u200F+(?=[.,;:\)\]\"])", "", text)

    # LRM (U+200E) after opening parenthesis/bracket is usually wrong
    text = re.sub(r"(?<=[(\[])\u200E+", "", text)

    # Multiple consecutive directional marks should be removed
    text = re.sub(r"[\u200E\u200F]{2,}", "", text)

    # 4. Flag (but don't auto-fix) orphan punctuation at paragraph start
    # This would require understanding sentence structure, so we just warn
    if re.match(r"^\s*[.,;:]", text):
        # Remove the orphan punctuation
        text = re.sub(r"^\s*([.,;:])", "", text).strip()

    return text


def set_rtl_para(para):
    """Enable RTL layout for a paragraph via w:bidi.

    w:bidi marks the paragraph as RTL so text flows right-to-left. Paragraph
    alignment (w:jc) is set separately by the caller via para.alignment, so
    this function only adds the bidi element to avoid duplicate jc elements.
    """
    pPr = para._p.get_or_add_pPr()
    bidi = OxmlElement("w:bidi")
    bidi.set(qn("w:val"), "1")
    pPr.append(bidi)


def set_rtl_run(run):
    """Enable RTL on a specific run via w:rtl in rPr element."""
    rPr = run._element.get_or_add_rPr()
    rtl_elem = OxmlElement("w:rtl")
    rPr.append(rtl_elem)


def _style_run(run, font_name, font_size, bold, italic, is_rtl):
    run.font.name = font_name
    run.font.size = Pt(font_size)
    run.bold = bold
    run.italic = italic
    if is_rtl:
        run._element.rPr.rFonts.set(qn("w:cs"), font_name)
        set_rtl_run(run)


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
):
    """
    Add a paragraph with proper RTL handling for Hebrew text.

    Key principle: Write text naturally, let DOCX handle bidirectional rendering.
    No manual insertion of directional marks.

    Args:
        doc: python-docx Document
        text: Paragraph text (Hebrew or mixed)
        font_name: Font name (e.g., "David")
        font_size: Font size in points
        is_rtl: Whether text is right-to-left
        bold, italic: Text formatting
        align: Paragraph alignment
        space_before, space_after: Spacing in points
        line_spacing: Line spacing multiplier (e.g., 1.5)

    Returns:
        The Paragraph object
    """
    # Validate and clean text (remove AI typography tells)
    text = validate_hebrew_text(text)

    # Create paragraph
    para = doc.add_paragraph()
    para.alignment = align
    para.paragraph_format.space_before = Pt(space_before)
    para.paragraph_format.space_after = Pt(space_after)
    para.paragraph_format.line_spacing = line_spacing

    if is_rtl:
        set_rtl_para(para)

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
                run = para.add_run(segment)
                _style_run(run, font_name, font_size, bold, italic, is_rtl)
            footnote_adder.add_footnote(para, "", fn_text)
            cursor = end
        tail = text[cursor:]
        if tail:
            run = para.add_run(tail)
            _style_run(run, font_name, font_size, bold, italic, is_rtl)
    else:
        run = para.add_run(text)
        _style_run(run, font_name, font_size, bold, italic, is_rtl)

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
):
    """Render a cover page (שער) as the first page of the document.

    Renders whichever fields are present in `cover` (skipping None/missing/
    empty-string fields), then inserts a page break so the article title
    that follows always starts on a fresh page. Reuses `add_para` /
    `set_rtl_para` / `_style_run` -- the same styling path used everywhere
    else in this file -- rather than a parallel one.
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
        )

    # Institutional header block: university / faculty / department.
    render(cover.get("university"), heading_size, bold=True, space_after=4)
    render(cover.get("faculty"), body_size, space_after=4)
    render(cover.get("department"), body_size, space_after=4)

    # Article title -- falls back to the top-level article title when the
    # cover page doesn't specify its own.
    cover_title = cover.get("title") or fallback_title
    render(cover_title, title_size, bold=True, space_before=36, space_after=24)

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

    # Article body must never share a page with the cover content.
    doc.add_page_break()


def generate_docx(data: dict, output_path: str):
    """Generate a .docx file from article data."""
    # Extract format settings with defaults
    fmt = data.get("format", {})
    font_name = fmt.get("font", "David")
    body_size = fmt.get("bodySize", 11)
    title_size = fmt.get("titleSize", 16)
    heading_size = fmt.get("headingSize", 13)
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
    show_section_titles = total_words > SECTION_TITLE_WORD_THRESHOLD

    title = data.get("title", "Untitled")
    thesis = data.get("thesis", None)
    sections = data.get("sections", [])

    # Rewrite intra-article footnote self-references ("לעיל, הערה N") from
    # each writer unit's own LOCAL footnote ordinal to the document-wide
    # GLOBAL ordinal FootnoteAdder is about to assign below. Must run
    # before the section/paragraph loop that calls add_para.
    sections, unresolved_backrefs = remap_backreferences(sections)
    warn_unresolved(unresolved_backrefs)

    doc = Document(TEMPLATE_PATH)
    doc._body.clear_content()
    footnote_adder = FootnoteAdder(is_rtl=is_rtl)

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

    # Cover page (שער) -- optional, additive. Renders first, before the
    # article title, and always ends with a page break so the article body
    # never shares a page with cover content.
    cover_page = data.get("coverPage")
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
        )

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
        )

    # Abstract(s)
    abstract_data = data.get("abstract", None)
    if abstract_data:
        primary_abstract = abstract_data.get("primary", None)
        secondary_abstract = abstract_data.get("secondary", None)

        if primary_abstract:
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
            )

        if secondary_abstract:
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
            )

    # Body sections
    for sec in sections:
        # Conditional section titles
        if show_section_titles:
            heading_align = (
                WD_ALIGN_PARAGRAPH.RIGHT if is_rtl else WD_ALIGN_PARAGRAPH.LEFT
            )
            add_para(
                doc,
                sec.get("title", ""),
                font_name,
                heading_size,
                is_rtl=is_rtl,
                bold=True,
                align=heading_align,
                space_before=12,
                space_after=6,
                line_spacing=line_spacing,
            )

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
            )

    add_page_numbers(doc)
    doc.save(output_path)
    footnote_adder.finalize_footnotes(output_path)
    print(f"Saved: {output_path}")
    print(f"Words: {total_words}")
    print(f"Sections: {len(sections)}")
    print(
        f"Section titles: {'shown' if show_section_titles else 'hidden (under ' + str(SECTION_TITLE_WORD_THRESHOLD) + ' words)'}"
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
