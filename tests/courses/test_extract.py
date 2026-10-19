"""Extraction on request: plan per kind, python text layer (Hebrew-aware, with a quality gate), and the queue drain."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "scripts" / "courses"))
import extract

fitz = pytest.importorskip("fitz")
docx = pytest.importorskip("docx")

HEBREW = ("בראשית ברא אלהים את השמים ואת הארץ והארץ היתה תהו ובהו וחשך על פני תהום ורוח אלהים מרחפת על פני המים "
          "ויאמר אלהים יהי אור ויהי אור וירא אלהים את האור כי טוב ויבדל אלהים בין האור ובין החשך")
FONTS = ["/Library/Fonts/Arial Unicode.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "C:/Windows/Fonts/arial.ttf"]
FONT = next((f for f in FONTS if Path(f).is_file()), None)
needs_font = pytest.mark.skipif(FONT is None, reason="no Hebrew-capable system font to build a test PDF")


def _w(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def make_pdf(path: Path, pages, visual=True) -> Path:
    """pages: strings (text pages) or None (an image-only page, like a scan).

    A real Hebrew PDF stores each line in visual order (left to right on the page) and the extractor restores logical
    order, so `visual=True` draws every line reversed. `visual=False` draws the logical string left to right, which is
    what a badly built PDF looks like: the extractor then returns reversed text and the quality gate must catch it."""
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        if text is None:
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), False)
            pix.clear_with(200)
            page.insert_image(fitz.Rect(50, 50, 300, 300), stream=pix.tobytes("png"))
            continue
        words, line, y = text.split(), [], 72
        for w in words + [""]:
            if w and len(" ".join(line + [w])) <= 40:
                line.append(w)
                continue
            if line:
                page.insert_text((60, y), (" ".join(line)[::-1] if visual else " ".join(line)), fontsize=12, fontname="F0", fontfile=FONT)
                y += 18
            line = [w] if w else []
    doc.save(str(path))
    doc.close()
    return path


def make_reg(tmp_path):
    reg = tmp_path / "T1"
    _w(reg / "term.json", {"term": "T1"})
    return reg


def add_source(reg, file, sha8="aaaaaaaa"):
    _w(reg / "cohen.json", {"slug": "cohen", "sources": [{"sha256": sha8 + "0" * 56, "sha8": sha8, "file": str(file), "title": "t"}]})


# --- the Hebrew gate (strings only) ---------------------------------------------------------------

def test_gate_accepts_logical_hebrew():
    assert extract.page_quality(HEBREW, expect_hebrew=True) == (True, "ok")


def test_gate_rejects_reversed_hebrew():
    ok, reason = extract.page_quality(HEBREW[::-1], expect_hebrew=True)
    assert not ok and reason == "reversed-hebrew"


def test_gate_rejects_isolated_letters_and_junk():
    spaced = " ".join(HEBREW.replace(" ", ""))
    assert extract.page_quality(spaced, expect_hebrew=True) == (False, "isolated-letters")
    assert extract.page_quality("(cid:12)(cid:40) " * 6)[1] == "garbled-glyphs"
    assert extract.page_quality("xqzt wrvk pdfg hjkl mnbv qwrt zxcv bnmk lkjh gfds rtyp", expect_hebrew=True)[1] == "latin-junk"
    assert extract.page_quality("   ")[1] == "no-text-layer"


def test_gate_leaves_latin_pages_alone_in_a_latin_document():
    assert extract.page_quality("The quick brown fox jumps over the lazy dog again and again", expect_hebrew=False)[0]


def test_maqaf_compounds_are_not_reversed():
    text = "מלך־ישראל " * 10 + "אלהים אלהים אלהים"
    assert extract.page_quality(text, expect_hebrew=True)[0]


def test_printed_page_number():
    assert extract.printed_page_number("כותרת\nטקסט\n47") == "47"
    assert extract.printed_page_number("12\nטקסט") == "12"
    assert extract.printed_page_number("טקסט בלי מספר") is None


# --- python extraction on generated files ----------------------------------------------------------

@needs_font
def test_python_path_returns_readable_logical_hebrew(tmp_path):
    pdf = make_pdf(tmp_path / "heb.pdf", [HEBREW + "\n", HEBREW])
    result = extract.run_text_layer(pdf)
    assert result["method"] == "pymupdf" and result["fallback"] == []
    joined = " ".join(" ".join(p["text"].split()) for p in result["pages"])
    for phrase in ("בראשית ברא אלהים", "השמים ואת הארץ", "וחשך על פני תהום"):
        assert phrase in joined  # logical order, words intact


@needs_font
def test_reversed_hebrew_pdf_falls_back_to_claude_vision_with_reason(tmp_path):
    pdf = make_pdf(tmp_path / "rev.pdf", [HEBREW, HEBREW], visual=False)  # drawn logical: extracts reversed
    good = make_pdf(tmp_path / "good.pdf", [HEBREW])
    doc = fitz.open(str(good))
    doc.insert_pdf(fitz.open(str(pdf)), to_page=1)
    doc.save(str(tmp_path / "mix.pdf"))
    result = extract.run_text_layer(tmp_path / "mix.pdf", expect_hebrew=True)
    assert [p["page"] for p in result["pages"]] == [1]
    assert result["fallback"] == [{"page": 2, "reason": "reversed-hebrew"}, {"page": 3, "reason": "reversed-hebrew"}][:1] or \
        [f["reason"] for f in result["fallback"]] == ["reversed-hebrew"] * len(result["fallback"])
    assert result["fallback"][0]["page"] == 2


@needs_font
def test_printed_page_numbers_are_kept_in_the_markdown(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((60, 72), HEBREW[:60][::-1], fontsize=12, fontname="F0", fontfile=FONT)
    page.insert_text((300, 800), "47", fontsize=10, fontname="F0", fontfile=FONT)
    doc.save(str(tmp_path / "num2.pdf"))
    result = extract.run_text_layer(tmp_path / "num2.pdf", expect_hebrew=True)
    md = extract.render_markdown("t", result)
    assert "## עמוד 47 <!-- pdf:1 -->" in md


def test_docx_text_is_extracted_without_a_model(tmp_path):
    path = tmp_path / "r.docx"
    d = docx.Document()
    d.add_paragraph("שלום עולם")
    d.add_paragraph("פסקה שנייה")
    d.save(str(path))
    result = extract.run_text_layer(path)
    assert result["method"] in ("python-docx", "pandoc")
    assert "שלום עולם" in result["pages"][0]["text"] and "פסקה שנייה" in result["pages"][0]["text"]


# --- plan ------------------------------------------------------------------------------------------

def job(*items, course="cohen"):
    return {"course": course, "items": list(items), "created_at": "2026-10-19T10:00:00+03:00"}


@needs_font
def test_plan_per_kind_and_method(tmp_path):
    reg = make_reg(tmp_path)
    text_pdf = make_pdf(tmp_path / "text.pdf", [HEBREW, HEBREW])
    scan_pdf = make_pdf(tmp_path / "scan.pdf", [None, None])
    mixed_pdf = make_pdf(tmp_path / "mixed.pdf", [HEBREW, None])
    doc_path = tmp_path / "r.docx"
    d = docx.Document()
    d.add_paragraph("טקסט")
    d.save(str(doc_path))
    _w(reg / "cohen.json", {"slug": "cohen", "sources": [
        {"sha256": "1" * 64, "sha8": "11111111", "file": str(doc_path)},
        {"sha256": "2" * 64, "sha8": "22222222", "file": str(text_pdf)},
        {"sha256": "3" * 64, "sha8": "33333333", "file": str(scan_pdf)},
        {"sha256": "4" * 64, "sha8": "44444444", "file": str(mixed_pdf)}]})
    _w(reg / "refs" / "cohen.json", {"course": "cohen", "refs": [{"key": "r-1", "citation": "x", "status": "downloaded", "download_path": str(scan_pdf)}]})
    by = {f"{p['kind']}:{p['key']}:{p['requested']}": p for p in extract.plan(job(
        {"kind": "source", "key": "11111111", "method": "auto"},
        {"kind": "source", "key": "22222222", "method": "auto"},
        {"kind": "source", "key": "33333333", "method": "auto"},
        {"kind": "source", "key": "44444444", "method": "auto"},
        {"kind": "ref", "key": "r-1", "method": "auto"},
        {"kind": "source", "key": "22222222", "method": "gemini-ocr"},
        {"kind": "source", "key": "22222222", "method": "tesseract"},
        {"kind": "source", "key": "22222222", "method": "claude-vision"},
        {"kind": "source", "key": "99999999", "method": "auto"}), reg)}
    assert (by["source:11111111:auto"]["action"], by["source:11111111:auto"]["method"]) == ("python", "python-docx")
    assert (by["source:22222222:auto"]["action"], by["source:22222222:auto"]["method"]) == ("python", "pymupdf")
    assert (by["source:33333333:auto"]["action"], by["source:33333333:auto"]["method"]) == ("claude", "claude-vision")  # scan
    assert by["source:44444444:auto"]["action"] == "python" and by["source:44444444:auto"]["scan_pages"] == [2]
    assert by["ref:r-1:auto"]["action"] == "claude"
    assert by["source:22222222:gemini-ocr"]["action"] == "external" and by["source:22222222:gemini-ocr"]["method"] == "gemini-ocr"
    assert by["source:22222222:tesseract"]["method"] == "tesseract"
    assert by["source:22222222:claude-vision"]["action"] == "claude"
    assert by["source:99999999:auto"]["action"] == "skip"
    assert not any(p["method"] == "pdftotext" for p in by.values())


# --- drain -----------------------------------------------------------------------------------------

@needs_font
def test_drain_extracts_python_items_hands_off_scans_and_moves_the_job(tmp_path):
    reg = make_reg(tmp_path)
    text_pdf = make_pdf(tmp_path / "text.pdf", [HEBREW])
    scan_pdf = make_pdf(tmp_path / "scan.pdf", [None])
    _w(reg / "cohen.json", {"slug": "cohen", "sources": [
        {"sha256": "2" * 64, "sha8": "22222222", "file": str(text_pdf)},
        {"sha256": "3" * 64, "sha8": "33333333", "file": str(scan_pdf)}]})
    _w(reg / "queue" / "extract" / "20261019T100000Z-cohen.json", job(
        {"kind": "source", "key": "22222222", "method": "auto"}, {"kind": "source", "key": "33333333", "method": "auto"}))
    dry = extract.drain(reg, dry_run=True)
    assert [j["status"] for j in dry["jobs"]] == ["done"] and not (reg / "extracted").exists()
    assert (reg / "queue" / "extract" / "20261019T100000Z-cohen.json").exists()
    report = extract.drain(reg)
    assert (reg / "extracted" / "cohen" / "source-22222222.md").is_file()
    assert "בראשית ברא אלהים" in (reg / "extracted" / "cohen" / "source-22222222.md").read_text(encoding="utf-8")
    assert not list((reg / "queue" / "extract").glob("*.json"))
    assert (reg / "queue" / "extract" / "done" / "20261019T100000Z-cohen.json").is_file()
    assert [h["key"] for h in report["handoff"]] == ["33333333"] and report["handoff"][0]["method"] == "claude-vision"
    assert "Write the text to" in report["handoff"][0]["instruction"]
    # once Claude has written the text the handoff disappears
    out = Path(report["handoff"][0]["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("## עמוד 1\n", encoding="utf-8")
    assert extract.pending_handoffs(reg) == []


@needs_font
def test_drain_hands_failed_gate_pages_to_claude(tmp_path):
    reg = make_reg(tmp_path)
    good, bad = make_pdf(tmp_path / "g.pdf", [HEBREW]), make_pdf(tmp_path / "b.pdf", [HEBREW], visual=False)
    doc = fitz.open(str(good))
    doc.insert_pdf(fitz.open(str(bad)))
    doc.save(str(tmp_path / "rev.pdf"))
    add_source(reg, tmp_path / "rev.pdf")
    _w(reg / "queue" / "extract" / "a-cohen.json", job({"kind": "source", "key": "aaaaaaaa", "method": "auto"}))
    report = extract.drain(reg)
    h = report["handoff"][0]
    assert h["pages"] == [2] and "reversed-hebrew" in h["reason"] and h["out"].endswith("source-aaaaaaaa.claude.md")
    meta = json.loads((reg / "extracted" / "cohen" / "source-aaaaaaaa.json").read_text(encoding="utf-8"))
    assert meta["fallback"] == [{"page": 2, "reason": "reversed-hebrew"}]


def test_drain_keeps_invalid_jobs_and_survives_a_missing_file(tmp_path):
    reg = make_reg(tmp_path)
    _w(reg / "cohen.json", {"slug": "cohen", "sources": [{"sha256": "5" * 64, "sha8": "55555555", "file": str(tmp_path / "gone.pdf")}]})
    _w(reg / "queue" / "extract" / "a.json", {"nonsense": True})
    _w(reg / "queue" / "extract" / "b-cohen.json", job({"kind": "source", "key": "55555555", "method": "auto"}))
    report = extract.drain(reg)
    assert report["jobs"][0]["status"] == "invalid" and (reg / "queue" / "extract" / "a.json").exists()
    assert report["jobs"][1]["results"]["source:55555555"]["state"] == "skipped"


def test_extract_never_shells_out_to_pdftotext():
    code = [ln for ln in Path(extract.__file__).read_text(encoding="utf-8").splitlines() if "subprocess" in ln or "shutil.which" in ln]
    assert code and not any("pdftotext" in ln for ln in code)


@needs_font
def test_a_chosen_source_with_a_pending_trove_job_is_flagged_for_ingest_and_the_job_is_left_alone(tmp_path):
    reg = make_reg(tmp_path)
    pdf = make_pdf(tmp_path / "t.pdf", [HEBREW])
    add_source(reg, pdf)
    sources_job = reg / "queue" / "sources" / "cohen-aaaaaaaa.json"
    _w(sources_job, {"slug": "cohen", "sha8": "aaaaaaaa"})
    other = reg / "queue" / "sources" / "cohen-bbbbbbbb.json"
    _w(other, {"slug": "cohen", "sha8": "bbbbbbbb"})
    _w(reg / "queue" / "extract" / "a-cohen.json", job({"kind": "source", "key": "aaaaaaaa", "method": "auto"}))
    report = extract.drain(reg)
    assert [i["key"] for i in report["ingest"]] == ["aaaaaaaa"] and sources_job.exists() and other.exists()
    sources_job.unlink()  # source-done moved it
    assert extract.pending_ingests(reg) == []


def test_refs_extract_queue_command_drains_and_prints_handoffs(tmp_path, capsys):
    import refs
    reg = make_reg(tmp_path)
    scan = make_pdf(tmp_path / "scan.pdf", [None])
    add_source(reg, scan)
    _w(reg / "queue" / "extract" / "a-cohen.json", job({"kind": "source", "key": "aaaaaaaa", "method": "auto"}))
    assert refs.main(["--registry", str(reg), "extract-queue", "--dry-run"]) == 0
    assert (reg / "queue" / "extract" / "a-cohen.json").exists() and "planned" in capsys.readouterr().out
    assert refs.main(["--registry", str(reg), "extract-queue"]) == 0
    out = capsys.readouterr().out
    assert "HANDOFF\tcohen\tsource:aaaaaaaa\tclaude-vision" in out
    assert (reg / "queue" / "extract" / "done" / "a-cohen.json").is_file()
    assert refs.main(["--registry", str(reg), "extract-queue"]) == 0 and "HANDOFF" in capsys.readouterr().out  # still waiting for Claude
