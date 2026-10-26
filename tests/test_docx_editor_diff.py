"""docx-editor-diff.py: extract -> chunk -> coverage on a synthetic edited/original pair."""
import json, subprocess, sys, pathlib
import pytest

ROOT = pathlib.Path(__file__).parent.parent
SCRIPT = ROOT / "src/scripts/docx-editor-diff.py"
sys.path.insert(0, str(ROOT / "tests/fixtures/docx"))
import editor_fixture  # noqa: E402


def run(*args, check=True):
    proc = subprocess.run([sys.executable, str(SCRIPT)] + [str(a) for a in args],
                          capture_output=True, text=True)
    if check:
        assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc


@pytest.fixture()
def files(tmp_path):
    return (editor_fixture.build(tmp_path / "edited.docx", True),
            editor_fixture.build(tmp_path / "original.docx", False), tmp_path / "work")


@pytest.fixture()
def extracted(files):
    edited, original, work = files
    run("extract", edited, "--original", original, "--work", work)
    return work


def ops_of(work):
    return json.loads((work / "extract/ops.json").read_text(encoding="utf-8"))


def test_extract_finds_body_footnote_and_format_ops(extracted):
    ops = ops_of(extracted)
    assert [o["id"] for o in ops] == ["op-%04d" % n for n in range(1, len(ops) + 1)]
    kinds = {(o["unit"].split(":")[0], o["kind"]) for o in ops}
    assert {("body", "text"), ("footnote", "text"), ("footnote", "run-format"),
            ("body", "run-format"), ("body", "paragraph-format"), ("body", "paragraph-mark")} <= kinds
    quote = next(o for o in ops if o.get("before") == 'ab"cd')
    assert "ASCII DOUBLE QUOTE" in quote["chars"] and "GERSHAYIM" in quote["chars"]


def test_font_churn_is_one_global_count(extracted):
    glob = json.loads((extracted / "extract/global.json").read_text(encoding="utf-8"))
    assert glob["global_format"] == {"font set to David": editor_fixture.CHURN_RUNS}
    assert not any(o["kind"] == "run-format" and o["text"].startswith("w0") for o in ops_of(extracted))


def test_extract_is_deterministic(files, extracted):
    edited, original, _ = files
    again = files[2].parent / "work2"
    run("extract", edited, "--original", original, "--work", again)
    assert ops_of(extracted) == ops_of(again)


def test_baseline_passes_for_matching_original_and_flags_a_different_one(files, tmp_path):
    edited, original, work = files
    out = run("extract", edited, "--original", original, "--work", work).stdout
    assert "body: 0, notes: 0" in out
    glob = json.loads((work / "extract/global.json").read_text(encoding="utf-8"))
    assert glob["baseline_checked"] and glob["baseline_diff_count"] == 0
    other = editor_fixture.build(tmp_path / "other.docx", True)  # not an original: its text differs
    proc = run("extract", edited, "--original", other, "--work", tmp_path / "w3", "--strict", check=False)
    assert proc.returncode == 1 and "body: 0" not in proc.stdout


def test_baseline_reports_a_changed_original(files, tmp_path):
    import zipfile
    edited, original, _ = files
    changed = tmp_path / "changed.docx"
    with zipfile.ZipFile(original) as zin, zipfile.ZipFile(changed, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = data.replace(b"This is important text.", b"This is quite important text.")
            zout.writestr(item, data)
    proc = run("extract", edited, "--original", changed, "--work", tmp_path / "w4", "--strict", check=False)
    assert proc.returncode == 1
    assert "body: 1" in proc.stdout


def test_chunk_keeps_footnote_with_its_paragraph_and_sets_marks_aside(extracted):
    run("chunk", "--work", extracted)
    chunks = extracted / "chunks"
    text = (chunks / "text-01.md").read_text(encoding="utf-8")
    assert text.index("## body:1 ") < text.index("## footnote:1 ") < text.index("## body:2 ")
    manifest = json.loads((chunks / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["unplaced"] == [] and manifest["total_ops"] == len(ops_of(extracted))
    auto = json.loads((chunks / "auto-classified.json").read_text(encoding="utf-8"))
    assert [a["rule_candidate"] for a in auto] == ["blank paragraph inserted"]
    layout_ids = json.loads((chunks / "layout.ids.json").read_text(encoding="utf-8"))
    text_ids = json.loads((chunks / "text-01.ids.json").read_text(encoding="utf-8"))
    everything = layout_ids + text_ids + [a["id"] for a in auto]
    assert sorted(everything) == [o["id"] for o in ops_of(extracted)]


def test_text_chunks_are_balanced(tmp_path):
    work = tmp_path / "work"
    (work / "extract").mkdir(parents=True)
    paragraphs, ops = [], []
    for n in range(100):  # 100 paragraphs of 5 ops each
        paragraphs.append({"part": "body", "idx": n, "page": 1, "style": "", "section": "S", "before": "a", "after": "b",
                           "fnrefs": [], "text_changed": True, "para_mark": "", "run_fmt": [], "para_fmt": None})
        for k in range(5):
            ops.append({"id": "op-%04d" % (len(ops) + 1), "kind": "text", "unit": "body:%d" % n, "page": 1, "op": "replace",
                        "before": "a", "after": "b", "chars": None, "ctx_before": "", "ctx_after": ""})
    (work / "extract/units.json").write_text(json.dumps({"paragraphs": paragraphs, "notes": []}))
    (work / "extract/ops.json").write_text(json.dumps(ops))
    (work / "extract/global.json").write_text("{}")
    run("chunk", "--work", work)
    manifest = json.loads((work / "chunks/manifest.json").read_text())
    sizes = [c["ops"] for c in manifest["chunks"] if c["name"].startswith("text-")]
    assert len(sizes) == 5 and max(sizes) - min(sizes) <= 5 and sum(sizes) == 500


def write_analysis(work, ids, name="text-01"):
    (work / "analysis").mkdir(exist_ok=True)
    (work / "analysis" / (name + ".json")).write_text(
        json.dumps([{"id": i, "category": "other"} for i in ids]), encoding="utf-8")


def test_coverage_passes_then_fails_on_missing_and_duplicate(extracted):
    run("chunk", "--work", extracted)
    chunks = extracted / "chunks"
    layout = json.loads((chunks / "layout.ids.json").read_text())
    text = json.loads((chunks / "text-01.ids.json").read_text())
    write_analysis(extracted, text, "text-01")
    write_analysis(extracted, layout, "layout")
    assert "coverage OK" in run("coverage", "--work", extracted).stdout
    write_analysis(extracted, text[1:], "text-01")  # one id left out
    proc = run("coverage", "--work", extracted, check=False)
    assert proc.returncode == 1 and "MISSING (1)" in proc.stdout and text[0] in proc.stdout
    write_analysis(extracted, text + layout[:1], "text-01")  # one id classified twice
    proc = run("coverage", "--work", extracted, check=False)
    assert proc.returncode == 1 and "DUPLICATED (1)" in proc.stdout
    write_analysis(extracted, text + ["op-9999"], "text-01")  # an id nobody extracted
    proc = run("coverage", "--work", extracted, check=False)
    assert proc.returncode == 1 and "UNKNOWN" in proc.stdout


def test_coverage_fails_without_any_analysis(extracted):
    run("chunk", "--work", extracted)
    proc = run("coverage", "--work", extracted, check=False)
    assert proc.returncode == 1 and "coverage FAILED" in proc.stdout


def test_merge_offers_only_skeptic_verified_wording(tmp_path):
    work = tmp_path / "work"
    (work / "synthesis").mkdir(parents=True)
    rules = [{"id": "R-01", "group": "g", "title": "t", "rule": "BROAD", "tier": "universal-hebrew-academic", "op_ids": []},
             {"id": "R-02", "group": "g", "title": "t", "rule": "BROAD", "tier": "noise", "op_ids": []},
             {"id": "R-03", "group": "g", "title": "t", "rule": "BROAD", "tier": "noise", "op_ids": []},
             {"id": "R-04", "group": "g", "title": "t", "rule": "BROAD", "tier": "noise", "op_ids": []},
             {"id": "R-05", "group": "g", "title": "t", "rule": "BROAD", "tier": "noise", "op_ids": []}]
    verdicts = [{"id": "R-01", "verdict": "narrow", "reason": "r", "corrected_rule": "NARROW", "applied_count": 9, "left_unchanged_count": 2},
                {"id": "R-02", "verdict": "refuted", "reason": "r", "corrected_rule": ""},
                {"id": "R-03", "verdict": "confirmed", "reason": "r", "corrected_rule": ""},
                {"id": "R-04", "verdict": "narrow", "reason": "r", "corrected_rule": ""}]
    (work / "synthesis/rules.json").write_text(json.dumps(rules))
    (work / "synthesis/verdicts.json").write_text(json.dumps(verdicts))
    decisions = tmp_path / "decisions.json"
    decisions.write_text(json.dumps({"R-01": {"decision": "adopt", "destination": "conventions"}}))
    proc = run("merge", "--work", work, "--decisions", decisions, "--strict", check=False)
    assert proc.returncode == 1 and "no verdict for R-05" in proc.stdout
    cat = {r["id"]: r for r in json.loads((work / "verified-catalogue.json").read_text())}
    assert cat["R-01"]["verified_rule"] == "NARROW" and cat["R-01"]["decision"]["decision"] == "adopt"
    assert cat["R-02"]["status"] == "refuted" and cat["R-02"]["verified_rule"] is None
    assert cat["R-03"]["verified_rule"] == "BROAD"
    assert cat["R-04"]["status"] == "needs-restatement" and cat["R-05"]["status"] == "unverified"
    md = (work / "verified-catalogue.md").read_text()
    assert "NARROW" in md and md.count("BROAD") == 1  # R-03 only; R-01's broad wording is not offered
    assert "## R-02" not in md and "## R-04" not in md and "## R-05" not in md
