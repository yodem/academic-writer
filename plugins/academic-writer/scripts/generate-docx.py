#!/usr/bin/env python3
"""
Academic Writer — DOCX Generator

Generates a properly formatted .docx file from article JSON data.
Handles RTL (Hebrew) text, citation parentheses, and conditional section titles.

Usage:
    python3 generate-docx.py --input article.json --output path.docx

Input JSON schema:
{
    "title": str,
    "thesis": str | null,
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
import re

from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


# --- Threshold for showing section titles ---
SECTION_TITLE_WORD_THRESHOLD = 1500


def fix_rtl_punctuation(text: str) -> str:
    """Fix RTL punctuation issues in Hebrew text.

    1. Insert RLM before '(' and LRM after ')' in citation contexts
    2. Fix punctuation at wrong position (start of word instead of end)
    """
    RLM = "\u200F"
    LRM = "\u200E"

    # Insert directional marks around all parentheses
    text = re.sub(r"\(", lambda m: RLM + "(", text)
    text = re.sub(r"\)", lambda m: ")" + LRM, text)

    # Fix punctuation at start of word (common RTL rendering issue)
    # Pattern: period or comma followed by a space then a word char at start
    text = re.sub(r"([.,;:])(\s+)(\S)", r"\2\3\1", text)

    return text


def split_mixed_direction_runs(text: str):
    """Split text into runs with explicit directionality.

    Detects citation parentheses and creates separate segments
    for RTL text and citation content.

    Returns list of (text, is_citation) tuples.
    """
    # Match citation parenthetical patterns: (content with author, title, page)
    citation_pattern = r"\([^)]+\)"
    parts = []
    last_end = 0

    for match in re.finditer(citation_pattern, text):
        # Text before citation
        if match.start() > last_end:
            parts.append((text[last_end:match.start()], False))
        # Citation itself
        parts.append((match.group(), True))
        last_end = match.end()

    # Remaining text after last citation
    if last_end < len(text):
        parts.append((text[last_end:], False))

    if not parts:
        parts = [(text, False)]

    return parts


def set_rtl_para(para):
    """Enable RTL layout for a paragraph via w:bidi."""
    pPr = para._p.get_or_add_pPr()
    bidi = OxmlElement("w:bidi")
    pPr.append(bidi)


def set_rtl_run(run):
    """Enable RTL on a specific run via w:rtl in rPr."""
    rPr = run._element.get_or_add_rPr()
    rtl_elem = OxmlElement("w:rtl")
    rPr.append(rtl_elem)


def add_para(doc, text, font_name, font_size, is_rtl=True,
             bold=False, italic=False,
             align=WD_ALIGN_PARAGRAPH.JUSTIFY,
             space_before=0, space_after=6,
             line_spacing=1.5):
    """Add a paragraph with proper RTL handling.

    For RTL text:
    - Sets w:bidi on paragraph
    - Sets w:rtl on every run's rPr
    - Splits mixed-direction content (citations vs prose) into separate runs
    - Inserts Unicode directional marks around parentheses
    """
    para = doc.add_paragraph()
    para.alignment = align
    para.paragraph_format.space_before = Pt(space_before)
    para.paragraph_format.space_after = Pt(space_after)
    para.paragraph_format.line_spacing = line_spacing

    if is_rtl:
        set_rtl_para(para)
        # Split into runs for mixed-direction content
        segments = split_mixed_direction_runs(text)
        for segment_text, is_citation in segments:
            if is_citation:
                # Fix RTL punctuation in citations
                segment_text = fix_rtl_punctuation(segment_text)
            run = para.add_run(segment_text)
            run.font.name = font_name
            run.font.size = Pt(font_size)
            run.bold = bold
            run.italic = italic
            # Set complex script font
            run._element.rPr.rFonts.set(qn("w:cs"), font_name)
            # Set RTL on every run
            set_rtl_run(run)
    else:
        run = para.add_run(text)
        run.font.name = font_name
        run.font.size = Pt(font_size)
        run.bold = bold
        run.italic = italic

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


def generate_docx(data: dict, output_path: str):
    """Generate a .docx file from article data."""
    # Extract format settings with defaults
    fmt = data.get("format", {})
    font_name = fmt.get("font", "David")
    body_size = fmt.get("bodySize", 11)
    title_size = fmt.get("titleSize", 16)
    heading_size = fmt.get("headingSize", 13)
    line_spacing = fmt.get("lineSpacing", 1.5)
    margin_inches = fmt.get("margins", 1.0)
    is_rtl = fmt.get("isRtl", True)

    total_words = data.get("totalWords", 0)
    show_section_titles = total_words > SECTION_TITLE_WORD_THRESHOLD

    title = data.get("title", "Untitled")
    thesis = data.get("thesis", None)
    sections = data.get("sections", [])

    doc = Document()

    # Set page margins
    for section in doc.sections:
        section.top_margin = Inches(margin_inches)
        section.bottom_margin = Inches(margin_inches)
        section.left_margin = Inches(margin_inches)
        section.right_margin = Inches(margin_inches)

    # Title (bold, centered)
    title_align = WD_ALIGN_PARAGRAPH.CENTER
    add_para(doc, title, font_name, title_size, is_rtl=is_rtl,
             bold=True, align=title_align, space_after=6,
             line_spacing=line_spacing)

    # Thesis subtitle (italic, centered) - always shown if present
    if thesis:
        add_para(doc, thesis, font_name, body_size, is_rtl=is_rtl,
                 italic=True, align=title_align, space_after=12,
                 line_spacing=line_spacing)

    # Abstract(s)
    abstract_data = data.get("abstract", None)
    if abstract_data:
        primary_abstract = abstract_data.get("primary", None)
        secondary_abstract = abstract_data.get("secondary", None)

        if primary_abstract:
            # Abstract heading
            abstract_heading = "תקציר" if is_rtl else "Abstract"
            add_para(doc, abstract_heading, font_name, heading_size,
                     is_rtl=is_rtl, bold=True,
                     align=(WD_ALIGN_PARAGRAPH.RIGHT if is_rtl
                            else WD_ALIGN_PARAGRAPH.LEFT),
                     space_before=12, space_after=6,
                     line_spacing=line_spacing)
            # Abstract body
            add_para(doc, primary_abstract, font_name, body_size,
                     is_rtl=is_rtl, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                     space_after=6, line_spacing=line_spacing)

        if secondary_abstract:
            # Secondary abstract (e.g., English abstract for Hebrew article)
            secondary_is_rtl = not is_rtl  # opposite direction
            add_para(doc, "Abstract", font_name, heading_size,
                     is_rtl=secondary_is_rtl, bold=True,
                     align=(WD_ALIGN_PARAGRAPH.RIGHT if secondary_is_rtl
                            else WD_ALIGN_PARAGRAPH.LEFT),
                     space_before=12, space_after=6,
                     line_spacing=line_spacing)
            add_para(doc, secondary_abstract, font_name, body_size,
                     is_rtl=secondary_is_rtl,
                     align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                     space_after=12, line_spacing=line_spacing)

    # Body sections
    for sec in sections:
        # Conditional section titles
        if show_section_titles:
            heading_align = (WD_ALIGN_PARAGRAPH.RIGHT if is_rtl
                             else WD_ALIGN_PARAGRAPH.LEFT)
            add_para(doc, sec.get("title", ""), font_name, heading_size,
                     is_rtl=is_rtl, bold=True, align=heading_align,
                     space_before=12, space_after=6,
                     line_spacing=line_spacing)

        # Section paragraphs
        for para_text in sec.get("paragraphs", []):
            add_para(doc, para_text, font_name, body_size, is_rtl=is_rtl,
                     align=WD_ALIGN_PARAGRAPH.JUSTIFY, space_after=6,
                     line_spacing=line_spacing)

    add_page_numbers(doc)
    doc.save(output_path)
    print(f"Saved: {output_path}")
    print(f"Words: {total_words}")
    print(f"Sections: {len(sections)}")
    print(f"Section titles: {'shown' if show_section_titles else 'hidden (under ' + str(SECTION_TITLE_WORD_THRESHOLD) + ' words)'}")


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
