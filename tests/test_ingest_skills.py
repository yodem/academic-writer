"""Contracts for the ingest and ingest-book skills.

These pin the parts the spec calls must-haves: printed-page preservation, the
page-1 reading-and-citation guide with three citation styles, OCR routed
through `aw ocr` with the real failure modes handled, the mandatory read-back,
the no-delete-without-confirmation rule, and the boundary between the two
skills. The frontmatter itself is checked by tests/test_frontmatter_keys.py
and test_skill_descriptions.py.
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent.parent
INGEST = ROOT / "src/skills/ingest/SKILL.md"
INGEST_BOOK = ROOT / "src/skills/ingest-book/SKILL.md"
TEMPLATE = ROOT / "src/skills/ingest/references/reading-page-template.md"


def _read(path):
    return path.read_text(encoding="utf-8")


def test_skills_exist_with_metadata():
    import re
    import yaml

    for path in (INGEST, INGEST_BOOK):
        text = _read(path)
        match = re.match(r"---\n(.*?)\n---\n", text, re.S)
        assert match, f"{path} has no frontmatter"
        fm = yaml.safe_load(match.group(1))
        meta = fm.get("metadata") or {}
        assert meta.get("version"), f"{path} metadata.version missing"
        assert "Use when" in str(fm.get("description", ""))
        assert "Do NOT use" in str(fm.get("description", ""))


def test_reading_page_template_has_three_citation_styles():
    text = _read(TEMPLATE)
    assert "How to read and cite" in text
    # style 1: Chicago notes-bibliography
    assert "Chicago notes-bibliography" in text
    # style 2: the Hebrew academic convention
    assert "Hebrew academic convention" in text
    assert "עמ׳" in text
    assert "תשנ״ה" in text
    # style 3: MLA or APA, chosen from the profile's citationStyle
    assert "MLA" in text and "APA" in text
    assert "citationStyle" in text
    # the citation rule and the marker forms
    assert "printed page number, never" in text or "never the book's sequential" in text
    assert "Original print page: NNN" in text or "orig. N" in text
    # primary-text structural locus
    assert "structural locus" in text.lower() or "structural-locus" in text.lower()
    assert "OCR, not image-verified" in text


def test_ingest_skill_contracts():
    text = _read(INGEST)
    # page 1 is the reading-and-citation guide
    assert "page 1" in text or "Page 1" in text
    assert "How to read and cite this book" in text
    # printed pages preserved and citable
    assert "printed page" in text
    # OCR through the plugin's own aw ocr, with the real failure modes
    assert "aw" in text and "ocr \\" in text
    assert '--data-dir "${CLAUDE_PLUGIN_DATA}"' in text
    assert "one page" in text or "One page" in text
    assert "upside down" in text
    assert "truncat" in text.lower()
    # mandatory read-back before claiming the upload
    assert "Read-back" in text
    assert "never say \"uploaded\"" in text.lower() or "Never say \"uploaded\"" in text
    # never delete or overwrite an existing book without confirmation
    assert "Never delete or overwrite" in text
    # page-number vs footnote-number disambiguation
    assert "footnote" in text
    # boundary with the sibling skill
    assert "/academic-writer:ingest-book" in text
    # profile scoping
    assert "profile.md" in text
    assert "trove" in text


def test_ingest_book_skill_contracts():
    text = _read(INGEST_BOOK)
    assert "page 1" in text or "Page 1" in text
    assert "How to read and cite this book" in text
    assert "printed page" in text
    # ToC metadata, not headings; every entry hinted
    assert "--toc" in text
    assert "hint" in text
    # OCR through aw ocr with the failure modes
    assert "aw" in text and "ocr \\" in text
    assert "MAX_TOKENS" in text
    assert "truncat" in text.lower()
    # mandatory read-back and the no-delete rule
    assert "Read-back" in text
    assert "Never delete or overwrite" in text
    # boundary with the sibling skill
    assert "/academic-writer:ingest" in text
    # scripts referenced by the skill exist and are runnable
    for script in ("extract_pdf.py", "build_crosswalk.py", "build_toc_enrich.py"):
        assert f"scripts/{script}" in text
        assert (ROOT / "src/scripts" / script).is_file()
    # references exist
    for ref in ("toc-mechanism.md", "epub-sources.md"):
        assert (ROOT / "src/skills/ingest-book/references" / ref).is_file()


def test_skills_cross_reference_and_do_not_contradict():
    ingest, book = _read(INGEST), _read(INGEST_BOOK)
    assert "/academic-writer:ingest" in book and "/academic-writer:ingest-book" in ingest
    # both state the same boundary rule
    for text in (ingest, book):
        assert "article" in text.lower() and "chapter" in text.lower()
        assert "100+" in text


def test_ingest_scripts_run_with_help_and_exit_zero():
    scripts = ROOT / "src/scripts"
    for script in ("extract_pdf.py", "build_crosswalk.py", "build_toc_enrich.py"):
        r = subprocess.run(
            [sys.executable, str(scripts / script), "-h"],
            capture_output=True, text=True)
        assert r.returncode == 0, f"{script} -h failed: {r.stderr}"


def test_extract_pdf_no_borrower_name_default():
    """The watermark drop list must not ship a real person's name by default."""
    text = _read(ROOT / "src/scripts/extract_pdf.py")
    assert "default=[]" in text or "default=[]" in text.replace(" ", "")
    assert "Yotam" not in text and "Fromm" not in text


def test_toc_enrich_appends_hints_and_maps_pages():
    """build_toc_enrich produces entries with hints appended and real Trove pages."""
    import json
    import tempfile

    script = ROOT / "src/scripts/build_toc_enrich.py"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        entries = [{"type": "unit", "label": "1", "title": "Chapter One",
                    "page": 5, "hint": "Opens the argument."}]
        (tmp / "entries.json").write_text(json.dumps(entries), encoding="utf-8")
        crosswalk = {"volumes": [
            {"volume": 1, "stored_to_ck": {"1": 2, "2": 3, "3": 4,
                                           "4": 5, "5": 6, "6": 7}}]}
        (tmp / "crosswalk.json").write_text(json.dumps(crosswalk), encoding="utf-8")
        cfg = {"reading_guide_title": "Guide", "volumes": [
            {"title": "Vol 1", "divider_ck": 2, "offset": 2,
             "ocr": str(tmp / "entries.json"), "xwalk_volume": 1}]}
        (tmp / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
        out = tmp / "toc.json"
        r = subprocess.run(
            [sys.executable, str(script), "--config", str(tmp / "cfg.json"),
             "--crosswalk", str(tmp / "crosswalk.json"), "--out", str(out)],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        toc = json.loads(out.read_text(encoding="utf-8"))
        assert toc[0] == {"title": "Guide", "page": 1, "level": 1}
        unit = [e for e in toc if "Chapter One" in e["title"]]
        assert len(unit) == 1
        # printed 5 + offset 2 = stored 7; stored 7 is past the crosswalk's
        # last mapped key (6), so the builder clamps to that page's Trove number
        assert unit[0]["page"] == 7
        assert unit[0]["level"] == 2
        assert unit[0]["title"].endswith("Opens the argument.")


def test_build_crosswalk_splits_volumes_on_number_reset():
    import json
    import tempfile

    script = ROOT / "src/scripts/build_crosswalk.py"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        md = ("# Reading Guide\n\n# עמוד מקורי 1\n\nbody\n"
              "# עמוד מקורי 2\n\nbody\n"
              "# כרך ב — divider\n\n# עמוד מקורי 1\n\nbody\n")
        combined = tmp / "combined.md"
        combined.write_text(md, encoding="utf-8")
        out = tmp / "crosswalk.json"
        r = subprocess.run(
            [sys.executable, str(script), str(combined), "--out", str(out)],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["total_ck_pages"] == 5
        assert [v["volume"] for v in data["volumes"]] == [1, 2]
        assert data["volumes"][0]["stored_to_ck"] == {"1": 2, "2": 3}
        assert data["volumes"][1]["stored_to_ck"] == {"1": 5}
        assert data["dividers"][0]["ck"] == 4
