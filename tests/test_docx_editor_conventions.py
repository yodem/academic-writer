"""Editor-review conventions in generate-docx.py (author decision 6, 2026-10-26).

Each test inspects the generated XML (document, styles, settings, footnotes,
footers). Rules: R-01/R-02 (no dash or quote conversion in the renderer),
R-60 fonts, R-61 note direction, R-62 heading styles, R-55 TOC field, R-63
unnumbered cover, R-59 new page per section. Synthetic data only.
"""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
import zipfile

from lxml import etree

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "src", "scripts")
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def _q(tag):
    return "{%s}%s" % (W_NS, tag)


def _load():
    spec = importlib.util.spec_from_file_location(
        "generate_docx_editor_conventions_test",
        os.path.join(SCRIPTS_DIR, "generate-docx.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load()

EN_NOTE = "Jane Doe, A Study of Things (Cambridge: Cambridge University Press, 1999), 42."
HE_NOTE = "פלוני אלמוני, מחקר לדוגמה (ירושלים, תשס\"ג), עמ' 7."
HE_NOTE_ENGLISH_TITLE = "ראו: A Very Long English Title of a Book About Many Different Things, 12."
EN_BIB = "Doe, Jane. A Study of Things. Cambridge: Cambridge University Press, 1999."
URL = "https://example.org/some/path"
HE_BIB = "אלמוני, פלוני. מחקר לדוגמה. ירושלים: הוצאה, תשס\"ג."
HE_MIXED = "פסקה בעברית עם מונח Cambridge University Press בתוך המשפט, ומספר 1999 גם כן."


def _sections():
    return [
        {"title": "מבוא", "paragraphs": [{
            "text": HE_MIXED,
            "footnotes": [
                {"after": "בתוך המשפט", "text": EN_NOTE},
                {"after": "ומספר", "text": HE_NOTE_ENGLISH_TITLE},
                {"after": "גם כן", "text": HE_NOTE},
            ],
        }]},
        {"title": "סעיף א", "paragraphs": ["פסקה ראשונה."],
         "subsections": [{"title": "תת-סעיף", "paragraphs": ["פסקה בתת-סעיף."]}]},
        {"title": "סעיף ב", "paragraphs": ["פסקה שנייה."]},
        {"title": "ביבליוגרפיה", "paragraphs": [EN_BIB, URL, HE_BIB]},
    ]


COVER = {"university": "אוניברסיטה לדוגמה", "author": "מחבר לדוגמה", "studentId": "000000000",
         "supervisor": "מנחה לדוגמה", "course": "סמינר לדוגמה", "date": "תשפ\"ו"}


def _data(sections=None, cover=None, fmt=None, abstract=None, words=2000, title="מאמר לדוגמה"):
    data = {
        "title": title,
        "totalWords": words,
        "format": {"isRtl": True, **(fmt or {})},
        "sections": sections if sections is not None else _sections(),
    }
    if cover:
        data["coverPage"] = cover
    if abstract:
        data["abstract"] = abstract
    return data


class Generated:
    """Parsed parts of one generated .docx."""

    def __init__(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.docx")
            MODULE.generate_docx(data, path)
            with zipfile.ZipFile(path) as zf:
                self.names = zf.namelist()
                self.parts = {n: zf.read(n) for n in self.names if n.endswith(".xml") or n.endswith(".rels")}
        self.document = etree.fromstring(self.parts["word/document.xml"])
        self.styles = etree.fromstring(self.parts["word/styles.xml"])
        self.settings = etree.fromstring(self.parts["word/settings.xml"])
        self.footnotes = etree.fromstring(self.parts["word/footnotes.xml"])

    def paragraphs(self):
        return self.document.findall(".//w:body/w:p", NS)

    @staticmethod
    def text(p):
        return "".join(p.xpath(".//w:t/text()", namespaces=NS))

    def para(self, startswith):
        for p in self.paragraphs():
            if self.text(p).startswith(startswith):
                return p
        raise AssertionError("no paragraph starting with %r" % startswith)

    def style(self, style_id):
        return self.styles.xpath(".//w:style[@w:styleId='%s']" % style_id, namespaces=NS)[0]

    def footnote_p(self, startswith):
        for p in self.footnotes.findall(".//w:footnote/w:p", NS):
            if self.text(p).strip().startswith(startswith):
                return p
        raise AssertionError("no footnote starting with %r" % startswith)

    def footers(self):
        out = {}
        for n, raw in self.parts.items():
            if n.startswith("word/footer"):
                out[n] = etree.fromstring(raw)
        return out

    def sect_pr(self):
        return self.document.findall(".//w:body/w:sectPr", NS)[-1]


def _val(el, attr="val"):
    return el.get(_q(attr)) if el is not None else None


def _text_run_rpr(p, needle):
    for r in p.findall("w:r", NS):
        if needle in "".join(r.xpath("w:t/text()", namespaces=NS)):
            return r.find("w:rPr", NS)
    raise AssertionError("no run containing %r" % needle)


class TypographyNotConvertedTests(unittest.TestCase):
    """Decisions 1 and 2: the renderer no longer touches dashes or quotes."""

    def test_em_dash_is_left_alone(self):
        self.assertEqual(MODULE.validate_hebrew_text("משפט — הערה — המשך"),
                         "משפט — הערה — המשך")

    def test_straight_quotes_are_left_alone(self):
        text = 'הוא אמר "דבר חשוב" ומיד אחר כך כתב תנ"ך'
        self.assertEqual(MODULE.validate_hebrew_text(text), text)
        self.assertNotIn("״", MODULE.validate_hebrew_text(text))

    def test_typed_gershayim_is_left_alone(self):
        self.assertEqual(MODULE.validate_hebrew_text("תנ״ך"), "תנ״ך")

    def test_directional_mark_cleanup_still_works(self):
        self.assertEqual(MODULE.validate_hebrew_text("שלום‏‏."), "שלום.")

    def test_document_keeps_em_dash_and_straight_quote(self):
        g = Generated(_data(sections=[{"title": "מבוא", "paragraphs": ['אמר "כך" — והלך.']}]))
        text = g.text(g.para("אמר"))
        self.assertIn(" — ", text)
        self.assertIn('"כך"', text)
        self.assertNotIn(" - ", text)
        self.assertNotIn("״", text)


class FontTests(unittest.TestCase):
    def test_doc_defaults_use_the_document_font_in_every_slot(self):
        g = Generated(_data())
        rfonts = g.styles.find("w:docDefaults/w:rPrDefault/w:rPr/w:rFonts", NS)
        for slot in ("ascii", "hAnsi", "cs", "eastAsia"):
            self.assertEqual(_val(rfonts, slot), "David")
        for theme in ("asciiTheme", "hAnsiTheme", "cstheme", "eastAsiaTheme"):
            self.assertIsNone(rfonts.get(_q(theme)))

    def test_hebrew_paragraph_with_latin_token_stays_david_in_every_slot(self):
        g = Generated(_data())
        rpr = _text_run_rpr(g.para("פסקה בעברית"), "Cambridge University Press")
        rfonts = rpr.find("w:rFonts", NS)
        self.assertEqual((_val(rfonts, "ascii"), _val(rfonts, "hAnsi"), _val(rfonts, "cs")),
                         ("David", "David", "David"))

    def test_latin_dominant_bibliography_and_url_use_times_new_roman(self):
        g = Generated(_data())
        for needle in ("Doe, Jane", "https://example.org"):
            rfonts = _text_run_rpr(g.para(needle), needle).find("w:rFonts", NS)
            self.assertEqual(_val(rfonts, "ascii"), "Times New Roman")
            self.assertEqual(_val(rfonts, "hAnsi"), "Times New Roman")
            self.assertEqual(_val(rfonts, "cs"), "David")

    def test_hebrew_bibliography_entry_stays_david(self):
        g = Generated(_data())
        rfonts = _text_run_rpr(g.para("אלמוני, פלוני"), "אלמוני").find("w:rFonts", NS)
        self.assertEqual(_val(rfonts, "ascii"), "David")

    def test_footnote_fonts_follow_dominant_script(self):
        g = Generated(_data())
        en = g.footnote_p("Jane Doe").findall("w:r", NS)[-1].find("w:rPr/w:rFonts", NS)
        he = g.footnote_p("פלוני").findall("w:r", NS)[-1].find("w:rPr/w:rFonts", NS)
        self.assertEqual((_val(en, "ascii"), _val(en, "hAnsi"), _val(en, "cs")),
                         ("Times New Roman", "Times New Roman", "David"))
        self.assertEqual((_val(he, "ascii"), _val(he, "hAnsi"), _val(he, "cs")),
                         ("David", "David", "David"))

    def _fonts(self, run):
        rfonts = run.find("w:rPr/w:rFonts", NS)
        return (_val(rfonts, "ascii"), _val(rfonts, "hAnsi"), _val(rfonts, "cs"),
                run.find("w:rPr/w:rtl", NS) is not None)

    def test_hebrew_words_inside_a_latin_note_get_their_own_david_rtl_run(self):
        # Word picks the font slot from the run's w:rtl flag, not the character
        # (verified by rendering), so cs=David alone would leave Hebrew in Times.
        note = "Doe, Jane, in ספר לדוגמה (Jerusalem, 1999), p. 7."
        sections = [{"title": "מבוא", "paragraphs": [{"text": "טקסט.", "footnotes": [{"after": "טקסט", "text": note}]}]}]
        g = Generated(_data(sections=sections))
        runs = g.footnote_p("Doe, Jane").findall("w:r", NS)[2:]
        by_text = {"".join(r.xpath("w:t/text()", namespaces=NS)): self._fonts(r) for r in runs}
        self.assertEqual(by_text["ספר לדוגמה"], ("David", "David", "David", True))
        self.assertEqual(by_text["Doe, Jane, in "], ("Times New Roman", "Times New Roman", "David", False))
        self.assertEqual("".join(by_text), note)

    def test_hebrew_words_inside_an_english_bibliography_entry_are_split_the_same_way(self):
        entry = "Doe, Jane. Title of a Book. Tel Aviv: ספרים, 1999."
        g = Generated(_data(sections=[{"title": "ביבליוגרפיה", "paragraphs": [entry]}]))
        runs = g.para("Doe, Jane").findall("w:r", NS)
        fonts = {"".join(r.xpath("w:t/text()", namespaces=NS)): self._fonts(r) for r in runs}
        self.assertEqual(fonts["ספרים"], ("David", "David", "David", True))
        self.assertEqual(fonts["Doe, Jane. Title of a Book. Tel Aviv: "][0], "Times New Roman")
        self.assertEqual("".join(fonts), entry)

    def test_hebrew_leading_note_with_english_title_is_david_throughout(self):
        g = Generated(_data())
        runs = g.footnote_p("ראו:").findall("w:r", NS)[2:]
        self.assertEqual(len(runs), 1)
        self.assertEqual(self._fonts(runs[0]), ("David", "David", "David", True))

    def test_latin_font_is_overridable_and_can_be_switched_off(self):
        g = Generated(_data(fmt={"latinFont": "Garamond"}))
        self.assertEqual(_val(_text_run_rpr(g.para("Doe, Jane"), "Doe").find("w:rFonts", NS), "ascii"),
                         "Garamond")
        for off in (None, ""):
            g = Generated(_data(fmt={"latinFont": off}))
            self.assertEqual(_val(_text_run_rpr(g.para("Doe, Jane"), "Doe").find("w:rFonts", NS), "ascii"),
                             "David")
            en = g.footnote_p("Jane Doe").findall("w:r", NS)[-1].find("w:rPr/w:rFonts", NS)
            self.assertEqual(_val(en, "ascii"), "David")

    def test_rtl_runs_carry_complex_script_bold_and_size(self):
        g = Generated(_data(cover=COVER))
        rpr = _text_run_rpr(g.para("מאמר לדוגמה"), "מאמר")
        self.assertIsNotNone(rpr.find("w:bCs", NS))
        self.assertEqual(_val(rpr.find("w:szCs", NS)), "32")
        tags = [c.tag.rsplit("}", 1)[-1] for c in rpr]
        self.assertEqual(tags, sorted(tags, key=MODULE._RPR_ORDER.index))


class NoteDirectionTests(unittest.TestCase):
    def test_latin_leading_footnote_is_ltr_left_without_rtl_runs(self):
        p = Generated(_data()).footnote_p("Jane Doe")
        self.assertEqual(_val(p.find("w:pPr/w:bidi", NS)), "0")
        self.assertEqual(_val(p.find("w:pPr/w:jc", NS)), "left")
        self.assertEqual(p.findall(".//w:rtl", NS), [])

    def test_hebrew_leading_footnote_stays_rtl_without_jc(self):
        g = Generated(_data())
        for start in ("פלוני", "ראו:"):  # the second has a long English title
            p = g.footnote_p(start)
            self.assertEqual(_val(p.find("w:pPr/w:bidi", NS)), "1")
            self.assertIsNone(p.find("w:pPr/w:jc", NS))
            self.assertEqual(len(p.findall(".//w:rtl", NS)), 1)

    def test_footnote_style_has_no_inherited_rtl_run_property(self):
        g = Generated(_data())
        self.assertEqual(g.style("FootnoteText").findall("w:rPr/w:rtl", NS), [])

    def test_bibliography_entries_follow_first_strong_character(self):
        g = Generated(_data())
        for start in ("Doe, Jane", "https://example.org"):
            p = g.para(start)
            self.assertEqual(_val(p.find("w:pPr/w:bidi", NS)), "0")
            self.assertEqual(_val(p.find("w:pPr/w:jc", NS)), "left")
            self.assertEqual(p.findall(".//w:r/w:rPr/w:rtl", NS), [])
        he = g.para("אלמוני, פלוני")
        self.assertEqual(_val(he.find("w:pPr/w:bidi", NS)), "1")
        self.assertEqual(len(he.findall(".//w:r/w:rPr/w:rtl", NS)), 1)

    def test_body_paragraph_is_not_flipped(self):
        g = Generated(_data(sections=[{"title": "מבוא", "paragraphs": ["Latin word first, then עברית."]}]))
        self.assertEqual(_val(g.para("Latin word").find("w:pPr/w:bidi", NS)), "1")

    def test_note_direction_document_opts_out(self):
        g = Generated(_data(fmt={"noteDirection": "document"}))
        self.assertEqual(_val(g.footnote_p("Jane Doe").find("w:pPr/w:bidi", NS)), "1")
        self.assertEqual(_val(g.para("Doe, Jane").find("w:pPr/w:bidi", NS)), "1")

    def test_helpers(self):
        from_module = MODULE.first_strong_direction
        self.assertEqual(from_module("1999. Doe"), "ltr")
        self.assertEqual(from_module("(12) שלום"), "rtl")
        self.assertIsNone(from_module("12, 34."))


class HeadingStyleTests(unittest.TestCase):
    def test_heading_styles_sizes_bold_black_document_font(self):
        g = Generated(_data())
        for sid, half_points in (("Heading1", "28"), ("Heading2", "24")):
            rpr = g.style(sid).find("w:rPr", NS)
            self.assertEqual(_val(rpr.find("w:sz", NS)), half_points)
            self.assertEqual(_val(rpr.find("w:szCs", NS)), half_points)
            self.assertIsNotNone(rpr.find("w:b", NS))
            self.assertIsNotNone(rpr.find("w:bCs", NS))
            color = rpr.find("w:color", NS)
            self.assertEqual(_val(color), "000000")
            self.assertIsNone(color.get(_q("themeColor")))
            rfonts = rpr.find("w:rFonts", NS)
            self.assertEqual(_val(rfonts, "ascii"), "David")
            self.assertIsNone(rfonts.get(_q("asciiTheme")))

    def test_every_heading_including_introduction_uses_the_style(self):
        g = Generated(_data())
        styles = {g.text(p): _val(p.find("w:pPr/w:pStyle", NS)) for p in g.paragraphs()
                  if p.find("w:pPr/w:pStyle", NS) is not None}
        self.assertEqual(styles["מבוא"], "Heading1")
        self.assertEqual(styles["סעיף א"], "Heading1")
        self.assertEqual(styles["תת-סעיף"], "Heading2")
        self.assertEqual(styles["ביבליוגרפיה"], "Heading1")

    def test_heading_runs_carry_no_direct_size_or_bold(self):
        g = Generated(_data())
        rpr = _text_run_rpr(g.para("סעיף א"), "סעיף א")
        for tag in ("sz", "szCs", "b", "bCs"):
            self.assertIsNone(rpr.find("w:" + tag, NS))

    def test_size_options(self):
        g = Generated(_data(fmt={"heading1Size": 16, "heading2Size": 13}))
        self.assertEqual(_val(g.style("Heading1").find("w:rPr/w:sz", NS)), "32")
        self.assertEqual(_val(g.style("Heading2").find("w:rPr/w:sz", NS)), "26")

    def test_legacy_headings_opt_out(self):
        g = Generated(_data(fmt={"headingStyles": False}))
        p = g.para("סעיף א")
        self.assertIsNone(p.find("w:pPr/w:pStyle", NS))
        self.assertEqual(_val(_text_run_rpr(p, "סעיף א").find("w:sz", NS)), "26")  # headingSize 13
        self.assertIsNone(g.style("Heading1").find("w:pPr/w:pageBreakBefore", NS))
        self.assertEqual(g.document.findall(".//w:instrText", NS), [])  # no TOC without styles


class TocTests(unittest.TestCase):
    def _instr(self, g):
        return [e.text for e in g.document.findall(".//w:instrText", NS)]

    def test_toc_field_structure_with_cover(self):
        g = Generated(_data(cover=COVER))
        self.assertEqual(self._instr(g), [' TOC \\o "1-2" \\h \\z \\u '])
        kinds = [e.get(_q("fldCharType")) for e in g.document.findall(".//w:fldChar", NS)]
        self.assertEqual(kinds, ["begin", "separate", "end"])
        entries = [g.text(p) for p in g.paragraphs()
                   if p.find("w:pPr/w:pStyle", NS) is not None
                   and _val(p.find("w:pPr/w:pStyle", NS)) in ("TOC1", "TOC2")]
        self.assertEqual(entries, ["מבוא", "סעיף א", "תת-סעיף", "סעיף ב", "ביבליוגרפיה"])
        # no page numbers are claimed: the cached result holds titles only
        self.assertFalse(any(ch.isdigit() for e in entries for ch in e))

    def test_toc_title_is_bold_14pt_and_not_itself_a_heading(self):
        g = Generated(_data(cover=COVER))
        p = g.para("תוכן העניינים")
        rpr = _text_run_rpr(p, "תוכן")
        self.assertEqual(_val(rpr.find("w:sz", NS)), "28")
        self.assertIsNotNone(rpr.find("w:b", NS))
        self.assertIsNone(p.find("w:pPr/w:pStyle", NS))

    def test_update_fields_in_settings(self):
        g = Generated(_data(cover=COVER))
        self.assertEqual(_val(g.settings.find("w:updateFields", NS)), "true")

    def test_toc_styles_exist_with_dot_leader_at_text_width(self):
        g = Generated(_data(cover=COVER))
        tab = g.style("TOC1").find("w:pPr/w:tabs/w:tab", NS)
        self.assertEqual((_val(tab), _val(tab, "leader")), ("right", "dot"))
        self.assertEqual(_val(tab, "pos"), "9026")  # A4 minus 1 inch margins
        self.assertIsNone(g.style("TOC1").get(_q("customStyle")))
        self.assertEqual(_val(g.style("TOC2").find("w:pPr/w:ind", NS), "left"), "240")

    def test_toc_with_cover_gets_its_own_page_and_title_starts_after_it(self):
        g = Generated(_data(cover=COVER))
        order = [g.text(p) for p in g.paragraphs() if g.text(p)]
        last_title = len(order) - 1 - order[::-1].index("מאמר לדוגמה")  # cover repeats the title
        self.assertLess(order.index("תוכן העניינים"), last_title)
        title = [p for p in g.paragraphs() if g.text(p) == "מאמר לדוגמה"][-1]
        self.assertIsNotNone(title.find("w:pPr/w:pageBreakBefore", NS))

    def test_auto_rule(self):
        three = _sections()[:3]
        four = _sections()
        self.assertEqual(Generated(_data(sections=three)).document.findall(".//w:instrText", NS), [])
        self.assertEqual(len(Generated(_data(sections=four)).document.findall(".//w:instrText", NS)), 1)
        # a cover page is enough
        self.assertEqual(len(Generated(_data(sections=three, cover=COVER)).document.findall(".//w:instrText", NS)), 1)
        # hidden headings (short article): nothing to collect
        short = Generated(_data(cover=COVER, words=500))
        self.assertEqual(short.document.findall(".//w:instrText", NS), [])
        self.assertIsNone(short.settings.find("w:updateFields", NS))

    def test_toc_option_forces_on_and_off(self):
        self.assertEqual(Generated(_data(sections=_sections()[:2], fmt={"toc": True}))
                         .document.findall(".//w:instrText", NS)[0].text, ' TOC \\o "1-2" \\h \\z \\u ')
        off = Generated(_data(cover=COVER, fmt={"toc": False}))
        self.assertEqual(off.document.findall(".//w:instrText", NS), [])
        self.assertIsNone(off.settings.find("w:updateFields", NS))

    def test_toc_without_cover_sits_before_the_first_section_on_its_own_page(self):
        g = Generated(_data())
        order = [g.text(p) for p in g.paragraphs() if g.text(p)]
        self.assertLess(order.index("מאמר לדוגמה"), order.index("תוכן העניינים"))
        self.assertLess(order.index("תוכן העניינים"), order.index("מבוא", order.index("תוכן העניינים") + 1))
        intro = [p for p in g.paragraphs() if g.text(p) == "מבוא"][-1]
        self.assertIsNone(intro.find("w:pPr/w:pageBreakBefore", NS))  # style carries the break


class CoverNumberingTests(unittest.TestCase):
    def test_cover_is_page_zero_with_title_page_and_empty_first_footer(self):
        g = Generated(_data(cover=COVER))
        sect = g.sect_pr()
        self.assertEqual(_val(sect.find("w:pgNumType", NS), "start"), "0")
        self.assertIsNotNone(sect.find("w:titlePg", NS))
        rels = etree.fromstring(g.parts["word/_rels/document.xml.rels"])
        targets = {r.get("Id"): r.get("Target") for r in rels}
        by_type = {}
        for ref in sect.findall("w:footerReference", NS):
            by_type[_val(ref, "type")] = targets[ref.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")]
        self.assertEqual(set(by_type), {"first", "default"})
        first = etree.fromstring(g.parts["word/" + by_type["first"]])
        default = etree.fromstring(g.parts["word/" + by_type["default"]])
        self.assertEqual(first.findall(".//w:instrText", NS), [])
        self.assertEqual(first.findall(".//w:fldChar", NS), [])
        self.assertEqual([e.text for e in default.findall(".//w:instrText", NS)], ["PAGE"])

    def test_pg_num_type_precedes_cols_and_title_pg_follows_it(self):
        sect = Generated(_data(cover=COVER)).sect_pr()
        tags = [c.tag.rsplit("}", 1)[-1] for c in sect]
        self.assertLess(tags.index("pgMar"), tags.index("pgNumType"))
        self.assertLess(tags.index("pgNumType"), tags.index("cols"))
        self.assertLess(tags.index("cols"), tags.index("titlePg"))

    def test_no_cover_means_normal_numbering(self):
        g = Generated(_data())
        sect = g.sect_pr()
        self.assertIsNone(sect.find("w:pgNumType", NS))
        self.assertIsNone(sect.find("w:titlePg", NS))
        self.assertEqual([e.text for f in g.footers().values() for e in f.findall(".//w:instrText", NS)], ["PAGE"])

    def test_cover_unnumbered_can_be_switched_off(self):
        sect = Generated(_data(cover=COVER, fmt={"coverUnnumbered": False})).sect_pr()
        self.assertIsNone(sect.find("w:pgNumType", NS))
        self.assertIsNone(sect.find("w:titlePg", NS))


class CoverLayoutTests(unittest.TestCase):
    LABELS = {"author": "LABEL-A:", "supervisor": "LABEL-S:", "course": "LABEL-C:"}

    def _texts_and_sizes(self, g):
        out = []
        for p in g.paragraphs():
            sz = p.find(".//w:r/w:rPr/w:sz", NS)
            out.append((g.text(p), _val(sz) if sz is not None else None))
        return out

    def test_compact_default_is_unchanged(self):
        g = Generated(_data(cover=COVER))
        self.assertEqual(dict(self._texts_and_sizes(g))["מחבר לדוגמה"], "22")  # body size

    def test_labeled_layout_label_line_then_value_line_with_size_tiers(self):
        cover = dict(COVER, layout="labeled", labels=self.LABELS, title="כותרת שער")
        g = Generated(_data(cover=cover))
        rows = self._texts_and_sizes(g)
        texts = [t for t, _ in rows]
        i = texts.index("LABEL-A:")
        self.assertEqual(texts[i + 1], "מחבר לדוגמה (000000000)")  # ID joins the name line
        self.assertEqual(texts[texts.index("LABEL-S:") + 1], "מנחה לדוגמה")
        self.assertEqual(texts[texts.index("LABEL-C:") + 1], "סמינר לדוגמה")
        sizes = dict(rows)
        self.assertEqual(sizes["כותרת שער"], "36")  # 18pt title
        for t in ("LABEL-A:", "מחבר לדוגמה (000000000)", "LABEL-S:", "סמינר לדוגמה"):
            self.assertEqual(sizes[t], "28")  # 14pt detail lines

    def test_labeled_layout_without_labels_renders_values_only(self):
        g = Generated(_data(cover=dict(COVER, layout="labeled")))
        texts = [g.text(p) for p in g.paragraphs()]
        self.assertIn("מנחה לדוגמה", texts)
        self.assertNotIn("מאת:", texts)  # no label is hard-coded in the plugin


class SectionPageTests(unittest.TestCase):
    def _blank_paragraphs(self, g):
        blanks = 0
        for p in g.paragraphs():
            if g.text(p) == "" and not p.findall(".//w:br", NS) and not p.findall(".//w:fldChar", NS) \
                    and not p.findall(".//w:footnoteReference", NS):
                blanks += 1
        return blanks

    def test_heading1_style_has_page_break_before_heading2_does_not(self):
        g = Generated(_data())
        self.assertIsNotNone(g.style("Heading1").find("w:pPr/w:pageBreakBefore", NS))
        self.assertIsNone(g.style("Heading2").find("w:pPr/w:pageBreakBefore", NS))

    def test_no_blank_paragraphs_are_used_for_spacing(self):
        self.assertEqual(self._blank_paragraphs(Generated(_data(cover=COVER))), 0)

    def test_first_heading_after_title_only_front_matter_has_no_break(self):
        g = Generated(_data(cover=COVER, fmt={"toc": False}))
        first = [p for p in g.paragraphs() if g.text(p) == "מבוא"][0]
        self.assertEqual(_val(first.find("w:pPr/w:pageBreakBefore", NS)), "0")
        second = [p for p in g.paragraphs() if g.text(p) == "סעיף א"][0]
        self.assertIsNone(second.find("w:pPr/w:pageBreakBefore", NS))  # inherits the style's break

    def test_first_heading_after_an_abstract_starts_a_new_page(self):
        g = Generated(_data(cover=COVER, fmt={"toc": False}, abstract={"primary": "תקציר קצר."}))
        first = [p for p in g.paragraphs() if g.text(p) == "מבוא"][0]
        self.assertIsNone(first.find("w:pPr/w:pageBreakBefore", NS))

    def test_cover_page_break_is_a_single_break_before_the_title_or_toc(self):
        g = Generated(_data(cover=COVER))
        breaks = g.document.findall(".//w:br[@w:type='page']", NS)
        self.assertEqual(len(breaks), 1)

    def test_consecutive_units_of_one_section_share_one_heading_and_one_page(self):
        sections = [
            {"title": "מבוא", "paragraphs": ["פתיחה."]},
            {"title": "סעיף א", "paragraphs": ["יחידה ראשונה."]},
            {"title": "סעיף א", "paragraphs": ["יחידה שנייה."]},
            {"title": "סעיף א", "paragraphs": ["סיכום הסעיף."]},
        ]
        g = Generated(_data(sections=sections))
        headings = [g.text(p) for p in g.paragraphs() if _val(p.find("w:pPr/w:pStyle", NS)) == "Heading1"]
        self.assertEqual(headings, ["מבוא", "סעיף א"])
        self.assertTrue(all(g.text(p) for p in g.paragraphs() if g.text(p) in ("יחידה שנייה.", "סיכום הסעיף.")))

    def test_merge_runs_after_back_reference_remap(self):
        # "לעיל, הערה 1" in the second unit points at ITS OWN first note; the
        # global ordinal must still be 2 after the units are merged.
        sections = [
            {"title": "סעיף", "paragraphs": [{"text": "יחידה אחת.", "footnotes": [{"after": "אחת", "text": "מקור א."}]}]},
            {"title": "סעיף", "paragraphs": [{"text": "יחידה שתיים.", "footnotes": [
                {"after": "שתיים", "text": "מקור ב."}]}, {"text": "עוד.", "footnotes": [
                    {"after": "עוד", "text": "ראו לעיל, הערה 1."}]}]},
        ]
        g = Generated(_data(sections=sections))
        note = g.footnote_p("ראו לעיל").xpath("string(.)")
        self.assertIn("הערה 2", note)

    def test_empty_title_renders_no_heading(self):
        g = Generated(_data(sections=[{"title": "", "paragraphs": ["גוף בלבד."]}]))
        self.assertEqual([p for p in g.paragraphs() if p.find("w:pPr/w:pStyle", NS) is not None], [])

    def test_section_starts_new_page_can_be_switched_off(self):
        g = Generated(_data(fmt={"sectionStartsNewPage": False}))
        self.assertIsNone(g.style("Heading1").find("w:pPr/w:pageBreakBefore", NS))

    def test_flat_level_two_entries_are_heading_two(self):
        sections = [{"title": "סעיף", "paragraphs": ["א."]}, {"title": "משנה", "level": 2, "paragraphs": ["ב."]}]
        g = Generated(_data(sections=sections))
        self.assertEqual(_val(g.para("משנה").find("w:pPr/w:pStyle", NS)), "Heading2")


class LtrDocumentTests(unittest.TestCase):
    def test_english_document_gets_ltr_footnotes_headings_and_times_text(self):
        sections = [{"title": "Introduction", "paragraphs": [{
            "text": "An English paragraph with a note.",
            "footnotes": [{"after": "a note", "text": EN_NOTE}]}]}]
        g = Generated(_data(sections=sections, fmt={"isRtl": False}, title="An Article"))
        note = g.footnote_p("Jane Doe")
        self.assertEqual(_val(note.find("w:pPr/w:bidi", NS)), "0")
        self.assertEqual(note.findall(".//w:rtl", NS), [])
        heading = g.para("Introduction")
        self.assertEqual(_val(heading.find("w:pPr/w:pStyle", NS)), "Heading1")
        self.assertIsNone(heading.find("w:pPr/w:bidi", NS))
        rfonts = _text_run_rpr(g.para("An English"), "An English").find("w:rFonts", NS)
        self.assertEqual(_val(rfonts, "ascii"), "Times New Roman")


if __name__ == "__main__":
    unittest.main()
