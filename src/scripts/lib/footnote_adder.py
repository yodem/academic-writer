"""
FootnoteAdder - Add real Word footnotes to python-docx documents.

This module provides the FootnoteAdder class that enables adding native
Word footnotes to documents created with python-docx.

Usage:
    from footnote_adder import FootnoteAdder
    from docx import Document

    doc = Document("footnote_template.docx")
    footnote_adder = FootnoteAdder()

    p = doc.add_paragraph()
    p.add_run("This needs a citation")
    footnote_adder.add_footnote(p, "", "Author, Book (2024), p. 42.")

    doc.save("output.docx")
    footnote_adder.finalize_footnotes("output.docx")
"""

from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from lxml import etree
import zipfile
import tempfile
import shutil
import os
import re
import unicodedata


def first_strong_direction(text):
    """Direction of the first strong character of ``text``.

    Returns ``"ltr"`` when the first strong character is Latin (or any other
    left-to-right letter), ``"rtl"`` when it is Hebrew/Arabic, and ``None``
    when the text has no strong character (digits, punctuation, spaces only).
    Paragraph direction of notes and bibliography entries follows this
    character, not the majority script: a Hebrew-leading note with a long
    English title stays RTL.
    """
    for ch in text or "":
        bidi_class = unicodedata.bidirectional(ch)
        if bidi_class == "L":
            return "ltr"
        if bidi_class in ("R", "AL"):
            return "rtl"
    return None


def latin_dominant(text):
    """True when ``text`` has more Latin-script letters than Hebrew/Arabic
    letters (English bibliography entries, English footnotes, URL lines).
    Used to pick the Latin font for a whole paragraph; Latin tokens inside a
    Hebrew-dominant paragraph keep the Hebrew font on purpose.
    """
    latin = rtl = 0
    for ch in text or "":
        if not ch.isalpha():
            continue
        bidi_class = unicodedata.bidirectional(ch)
        if bidi_class == "L":
            latin += 1
        elif bidi_class in ("R", "AL"):
            rtl += 1
    return latin > rtl


_RTL_LETTERS = "\u0590-\u05ff\ufb1d-\ufb4f\u0600-\u06ff"
_RTL_SEGMENT = re.compile(
    "[%s]+(?:[ \u00a0\"'\u2019][%s]+)*" % (_RTL_LETTERS, _RTL_LETTERS)
)


def split_rtl_segments(text):
    """Split ``text`` into ``[(chunk, is_rtl)]``: Hebrew/Arabic stretches
    (a run of letters, joined across single spaces or quote marks) versus
    everything else. Used in LTR paragraphs, where Word chooses the font slot
    by the run's ``w:rtl`` flag and not by the character, so a Hebrew word
    only gets the Hebrew font when it sits in its own ``w:rtl`` run.
    """
    chunks = []
    cursor = 0
    for match in _RTL_SEGMENT.finditer(text or ""):
        if match.start() > cursor:
            chunks.append((text[cursor:match.start()], False))
        chunks.append((match.group(0), True))
        cursor = match.end()
    if cursor < len(text or ""):
        chunks.append((text[cursor:], False))
    return chunks


def paragraph_fonts(text, font_name, latin_font, rtl=False):
    """(ascii/hAnsi font, complex-script font) for a paragraph of ``text``.

    The Latin font is used only for a Latin-dominant LTR paragraph (English
    bibliography entry, English footnote, URL line); the Hebrew words inside
    it must then be split into their own RTL runs (``split_rtl_segments``) to
    keep ``font_name``. An RTL paragraph, Hebrew-leading with whatever
    English in it, keeps ``font_name`` for every character: Word picks the
    font slot of an RTL run from its complex-script setting, so a Latin token
    inside a Hebrew sentence never switches font. ``latin_font`` falsy
    switches the behaviour off.
    """
    if latin_font and not rtl and latin_dominant(text):
        return latin_font, font_name
    return font_name, font_name


class FootnoteAdder:
    """Helper class to add real Word footnotes to documents."""

    def __init__(self, is_rtl: bool = False, font_name=None, latin_font=None,
                 auto_direction: bool = True):
        """Initialize FootnoteAdder.

        Args:
            is_rtl: Document direction. When True, footnote paragraphs and
                    text runs get RTL direction elements (w:bidi, w:rtl).
                    Set this to True for Hebrew/Arabic documents.
            font_name: Font for the footnote text (all slots). None leaves
                    the font to the document defaults.
            latin_font: Font for Latin-dominant footnotes (e.g. Times New
                    Roman); None keeps ``font_name`` for every footnote.
            auto_direction: When True (default) each footnote paragraph
                    follows its first strong character: Latin-leading is an
                    LTR left-aligned paragraph (w:bidi val=0, w:jc left,
                    runs without w:rtl), Hebrew-leading is RTL. A note with
                    no strong character follows ``is_rtl``. False gives
                    every note the document direction.
        """
        self.footnote_id = 0
        self.footnotes_to_add = []
        self.is_rtl = is_rtl
        self.font_name = font_name
        self.latin_font = latin_font
        self.auto_direction = auto_direction

    def _note_is_rtl(self, text):
        """Effective direction of one footnote paragraph."""
        if self.auto_direction:
            strong = first_strong_direction(text)
            if strong == "ltr":
                return False
            if strong == "rtl":
                return True
        return self.is_rtl

    def add_footnote(self, paragraph, text, footnote_text):
        """Add a footnote reference to a paragraph.

        Args:
            paragraph: The python-docx paragraph object
            text: Text to add before the footnote reference (can be empty string)
            footnote_text: The footnote content

        Returns:
            The footnote run object
        """
        self.footnote_id += 1

        if text:
            paragraph.add_run(text)

        # Create the footnote reference run
        footnote_run = paragraph.add_run()
        r = footnote_run._r

        # Add run properties with FootnoteReference style
        rPr = OxmlElement('w:rPr')
        rStyle = OxmlElement('w:rStyle')
        rStyle.set(qn('w:val'), 'FootnoteReference')
        rPr.append(rStyle)
        r.insert(0, rPr)

        # Add the footnote reference element
        footnote_ref = OxmlElement('w:footnoteReference')
        footnote_ref.set(qn('w:id'), str(self.footnote_id))
        r.append(footnote_ref)

        self.footnotes_to_add.append((self.footnote_id, footnote_text))
        return footnote_run

    def finalize_footnotes(self, docx_path):
        """Add all queued footnotes to the document. Call after doc.save().

        Args:
            docx_path: Path to the saved .docx file
        """
        if not self.footnotes_to_add:
            return

        extract_dir = tempfile.mkdtemp()

        try:
            with zipfile.ZipFile(docx_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # Update footnotes.xml
            footnotes_path = os.path.join(extract_dir, "word", "footnotes.xml")
            tree = etree.parse(footnotes_path)
            root = tree.getroot()
            w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

            for fn_id, fn_text in self.footnotes_to_add:
                footnote = etree.SubElement(root, "{%s}footnote" % w_ns)
                footnote.set("{%s}id" % w_ns, str(fn_id))

                p = etree.SubElement(footnote, "{%s}p" % w_ns)
                pPr = etree.SubElement(p, "{%s}pPr" % w_ns)
                pStyle = etree.SubElement(pPr, "{%s}pStyle" % w_ns)
                pStyle.set("{%s}val" % w_ns, "FootnoteText")

                note_rtl = self._note_is_rtl(fn_text)
                if note_rtl:
                    bidi_el = etree.SubElement(pPr, "{%s}bidi" % w_ns)
                    bidi_el.set("{%s}val" % w_ns, "1")
                    # No w:jc: in a <w:bidi/> paragraph Word renders jc="right" at the
                    # LEFT margin; the bidi default (start) is the right margin.
                else:
                    # LTR note (Latin-leading, or an LTR document): explicit
                    # bidi=0 overrides the FootnoteText style, left aligned.
                    bidi_el = etree.SubElement(pPr, "{%s}bidi" % w_ns)
                    bidi_el.set("{%s}val" % w_ns, "0")
                    jc_el = etree.SubElement(pPr, "{%s}jc" % w_ns)
                    jc_el.set("{%s}val" % w_ns, "left")

                # Footnote reference mark (superscript via FootnoteReference style)
                r1 = etree.SubElement(p, "{%s}r" % w_ns)
                rPr1 = etree.SubElement(r1, "{%s}rPr" % w_ns)
                rStyle1 = etree.SubElement(rPr1, "{%s}rStyle" % w_ns)
                rStyle1.set("{%s}val" % w_ns, "FootnoteReference")
                etree.SubElement(r1, "{%s}footnoteRef" % w_ns)

                # Space after reference
                r2 = etree.SubElement(p, "{%s}r" % w_ns)
                t2 = etree.SubElement(r2, "{%s}t" % w_ns)
                t2.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                t2.text = " "

                # Footnote text: explicit fonts, and w:rtl only on RTL notes.
                # A Latin-font note (LTR) puts its Hebrew words in their own
                # RTL runs so they keep the Hebrew font.
                ascii_font = cs_font = None
                if self.font_name:
                    ascii_font, cs_font = paragraph_fonts(
                        fn_text, self.font_name, self.latin_font, rtl=note_rtl
                    )
                split = bool(self.font_name) and not note_rtl and ascii_font != cs_font
                chunks = split_rtl_segments(fn_text) if split else [(fn_text, note_rtl)]
                for chunk, chunk_rtl in chunks:
                    r3 = etree.SubElement(p, "{%s}r" % w_ns)
                    if self.font_name or chunk_rtl:
                        rPr3 = etree.SubElement(r3, "{%s}rPr" % w_ns)
                        if self.font_name:
                            font = cs_font if chunk_rtl else ascii_font
                            rf = etree.SubElement(rPr3, "{%s}rFonts" % w_ns)
                            rf.set("{%s}ascii" % w_ns, font)
                            rf.set("{%s}hAnsi" % w_ns, font)
                            rf.set("{%s}cs" % w_ns, cs_font)
                        if chunk_rtl:
                            etree.SubElement(rPr3, "{%s}rtl" % w_ns)
                    t3 = etree.SubElement(r3, "{%s}t" % w_ns)
                    t3.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                    t3.text = chunk

            tree.write(footnotes_path, xml_declaration=True, encoding="UTF-8", standalone="yes")

            # Clean up Mac-specific content and fix XML
            self._cleanup_docx(extract_dir)

            # Repack with proper file order
            self._repack_docx(extract_dir, docx_path)

        finally:
            shutil.rmtree(extract_dir)

    def _cleanup_docx(self, extract_dir):
        """Remove Mac-specific elements and fix XML formatting."""

        for root_dir, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.endswith('.xml') or file.endswith('.rels'):
                    file_path = os.path.join(root_dir, file)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    modified = False

                    # Remove Mac namespaces
                    if 'xmlns:mo=' in content or 'xmlns:mv=' in content:
                        content = re.sub(r'\s*xmlns:mo="[^"]*"', '', content)
                        content = re.sub(r'\s*xmlns:mv="[^"]*"', '', content)
                        modified = True

                    # Fix single-quote XML declarations
                    if "<?xml version='1.0'" in content:
                        content = content.replace(
                            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>",
                            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        )
                        modified = True

                    if modified:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)

        # Fix webSettings.xml
        ws_path = os.path.join(extract_dir, "word", "webSettings.xml")
        if os.path.exists(ws_path):
            with open(ws_path, 'r', encoding='utf-8') as f:
                content = f.read()
            content = re.sub(r'\s*<w:doNotSaveAsSingleFile/>', '', content)
            with open(ws_path, 'w', encoding='utf-8') as f:
                f.write(content)

        # Fix settings.xml
        settings_path = os.path.join(extract_dir, "word", "settings.xml")
        if os.path.exists(settings_path):
            with open(settings_path, 'r', encoding='utf-8') as f:
                content = f.read()
            content = re.sub(r'<w:zoom w:val="bestFit"/>', '<w:zoom w:percent="100"/>', content)
            with open(settings_path, 'w', encoding='utf-8') as f:
                f.write(content)

        # Fix docProps/app.xml
        app_path = os.path.join(extract_dir, "docProps", "app.xml")
        if os.path.exists(app_path):
            with open(app_path, 'r', encoding='utf-8') as f:
                content = f.read()
            content = content.replace('Microsoft Macintosh Word', 'Microsoft Office Word')
            content = content.replace('<Manager/>', '<Manager></Manager>')
            content = content.replace('<Company/>', '<Company></Company>')
            content = content.replace('<HyperlinkBase/>', '<HyperlinkBase></HyperlinkBase>')
            with open(app_path, 'w', encoding='utf-8') as f:
                f.write(content)

    def _repack_docx(self, extract_dir, docx_path):
        """Repack the docx with proper OOXML file order."""
        all_files = []
        for root_dir, dirs, files in os.walk(extract_dir):
            for file in files:
                file_path = os.path.join(root_dir, file)
                arcname = os.path.relpath(file_path, extract_dir).replace('\\', '/')
                all_files.append((file_path, arcname))

        # OOXML requires specific file order
        priority_order = [
            '[Content_Types].xml',
            '_rels/.rels',
            'word/_rels/document.xml.rels',
            'word/document.xml',
            'word/footnotes.xml',
            'word/endnotes.xml',
        ]

        def sort_key(item):
            try:
                return (priority_order.index(item[1]), item[1])
            except ValueError:
                return (len(priority_order), item[1])

        all_files.sort(key=sort_key)

        temp_docx = docx_path + ".tmp"
        with zipfile.ZipFile(temp_docx, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path, arcname in all_files:
                zipf.write(file_path, arcname)

        os.replace(temp_docx, docx_path)
