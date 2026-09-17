"""Tests for src/scripts/extract-voice-exemplars.py.

The script feeds real author paragraphs to Gemini as voice examples, so what it
must never do is (a) pick a paragraph that cites nothing, which on a real corpus
was a colloquial course reflection, or (b) show Gemini the same paragraph twice
because two copies differ only by an invisible bidi mark.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "src", "scripts", "extract-voice-exemplars.py")

spec = importlib.util.spec_from_file_location("extract_voice_exemplars", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

CFG = json.load(open(os.path.join(REPO, "src", "thresholds.json"), encoding="utf-8"))["voice"]["exemplars"]


def para(n, cite=True, quote=True):
    body = " ".join(["מילה%d" % i for i in range(55)])
    q = ' הוא כותב "ציטוט קצר מן המקור" ומכאן עולה פרשנות' if quote else ""
    c = " (שם, עמ' %d)" % n if cite else ""
    return "פסקה %d %s.%s%s. משפט נוסף לסיום." % (n, body, q, c)


class TestSelection(unittest.TestCase):
    def select(self, texts, count=CFG["count"], per_file=CFG["maxPerFile"]):
        return mod.select_exemplars(texts, "hebrew", count, CFG["minWords"], CFG["maxWords"], per_file)

    def test_paragraph_without_citation_is_never_picked(self):
        texts = {"a.md": para(1, cite=False) + "\n\n" + para(2)}
        picked = [e["text"] for e in self.select(texts)]
        self.assertEqual(len(picked), 1)
        self.assertIn("פסקה 2", picked[0])

    def test_invisible_bidi_difference_is_deduplicated(self):
        text = para(3)
        texts = {"a.md": text, "b.md": text.replace(" ", " ‏", 1)}
        self.assertEqual(len(self.select(texts)), 1)

    def test_multiple_files_respect_max_per_file(self):
        texts = {"a.md": "\n\n".join(para(i) for i in range(1, 6)), "b.md": para(9)}
        picked = self.select(texts)
        per_file = {}
        for e in picked:
            per_file[e["file"]] = per_file.get(e["file"], 0) + 1
        self.assertTrue(all(v <= CFG["maxPerFile"] for v in per_file.values()), per_file)

    def test_single_chosen_file_can_supply_every_exemplar(self):
        texts = {"best.md": "\n\n".join(para(i) for i in range(1, 8))}
        self.assertEqual(len(self.select(texts)), CFG["count"])

    def test_analysis_after_quote_is_preferred(self):
        texts = {"a.md": para(1, quote=False) + "\n\n" + para(2, quote=True)}
        picked = self.select(texts, count=1, per_file=1)
        self.assertIn("פסקה 2", picked[0]["text"])

    def test_deterministic(self):
        texts = {"a.md": "\n\n".join(para(i) for i in range(1, 8)), "b.md": para(20)}
        self.assertEqual(self.select(texts), self.select(texts))


class TestCli(unittest.TestCase):
    def test_writes_file_the_mcp_bundle_can_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "paper.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("\n\n".join(para(i) for i in range(1, 6)))
            out = os.path.join(tmp, ".academic-helper", "voice-exemplars.md")
            proc = subprocess.run([sys.executable, SCRIPT, src, "--output", out], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            content = open(out, encoding="utf-8").read()
            # Same split rule as parseExemplarsFile in the MCP bundle.
            blocks = [b for b in content.split("\n---\n") if b.strip()]
            self.assertEqual(len(blocks), CFG["count"])
            self.assertTrue(content.startswith("# Voice exemplars"))

    def test_no_eligible_paragraph_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "notes.md")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("קצר מדי.")
            proc = subprocess.run([sys.executable, SCRIPT, src], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)


if __name__ == "__main__":
    unittest.main()
