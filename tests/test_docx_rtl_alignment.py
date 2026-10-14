"""Regression coverage for RTL heading and footnote alignment in DOCX output."""

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


def _load_generator():
    script_path = os.path.join(SCRIPTS_DIR, "generate-docx.py")
    spec = importlib.util.spec_from_file_location("generate_docx_rtl_alignment_test", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RtlAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.module = _load_generator()

    def test_heading_and_footnote_have_valid_rtl_alignment_order(self):
        data = {
            "title": "כותרת",
            "totalWords": 1501,
            "format": {"isRtl": True},
            "sections": [{
                "title": "רקע: כותרת סעיף",
                "paragraphs": [{
                    "text": "פסקה עם הערת שוליים.",
                    "footnotes": [{"after": "שוליים", "text": "מקור לדוגמה."}],
                }],
            }],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "out.docx")
            self.module.generate_docx(data, output_path)
            with zipfile.ZipFile(output_path) as zf:
                document = etree.fromstring(zf.read("word/document.xml"))
                footnotes = etree.fromstring(zf.read("word/footnotes.xml"))

        heading_ppr = document.xpath(
            ".//w:p[w:r/w:t='רקע: כותרת סעיף']/w:pPr", namespaces=NS
        )[0]
        footnote_ppr = footnotes.xpath(".//w:footnote[@w:id='1']/w:p/w:pPr", namespaces=NS)[0]

        for ppr in (heading_ppr, footnote_ppr):
            tags = [child.tag.rsplit("}", 1)[-1] for child in ppr]
            # RTL headings/footnotes carry <w:bidi/> and NO w:jc: Word renders
            # jc="right" in a bidi paragraph at the LEFT margin, while the bidi
            # default (start) is the right margin.
            self.assertIn("bidi", tags)
            self.assertIsNone(ppr.find("w:jc", namespaces=NS))

    def test_footnote_style_keeps_bidi_before_spacing_and_alignment(self):
        with zipfile.ZipFile(os.path.join(SCRIPTS_DIR, "lib", "footnote_template.docx")) as zf:
            styles = etree.fromstring(zf.read("word/styles.xml"))

        ppr = styles.xpath(".//w:style[@w:styleId='FootnoteText']/w:pPr", namespaces=NS)[0]
        tags = [child.tag.rsplit("}", 1)[-1] for child in ppr]
        self.assertLess(tags.index("bidi"), tags.index("spacing"))
        self.assertNotIn("jc", tags)  # bidi default aligns right; jc=right would render left


if __name__ == "__main__":
    unittest.main()
