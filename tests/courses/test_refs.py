import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "scripts" / "courses"))
import refs  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "refs"
PANDOC_MD = (FIXTURES / "pandoc_sample.md").read_text(encoding="utf-8")


def no_network(*_args, **_kwargs):
    raise AssertionError("network used in an offline test")


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    monkeypatch.setattr(refs, "fetch_url", no_network)
    monkeypatch.setattr(refs.urllib.request, "urlopen", no_network)


def make_registry(tmp_path, slug="nevua"):
    reg = tmp_path / "reg"
    reg.mkdir()
    (reg / "term.json").write_text(json.dumps({"term": "T"}), encoding="utf-8")
    (reg / f"{slug}.json").write_text(json.dumps({"slug": slug, "name": "נבואה"}), encoding="utf-8")
    return reg


def write_refs(reg, slug, refs_list, **extra):
    (reg / "refs").mkdir(exist_ok=True)
    payload = {"course": slug, "_note": "keep me", "refs": refs_list, **extra}
    (reg / "refs" / f"{slug}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def ref(key, status="pending", citation="ציטוט", **extra):
    base = {"key": key, "citation": citation, "pages_cited": "", "role": "quoted",
            "found_in": "lesson 1", "status": status, "note": ""}
    return {**base, **extra}


def build_docx(path):
    """A tiny docx with two footnotes, built in the test so no binary is committed."""
    ns = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
    content_types = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                     '<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>'
                     '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    doc_rels = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/>'
                '</Relationships>')
    document = (f'<?xml version="1.0" encoding="UTF-8"?><w:document {ns}><w:body><w:p>'
                '<w:r><w:t>טקסט ראשון</w:t></w:r><w:r><w:footnoteReference w:id="1"/></w:r>'
                '<w:r><w:t xml:space="preserve"> ועוד </w:t></w:r><w:r><w:footnoteReference w:id="2"/></w:r>'
                '</w:p></w:body></w:document>')
    footnotes = (f'<?xml version="1.0" encoding="UTF-8"?><w:footnotes {ns}>'
                 '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
                 '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
                 '<w:footnote w:id="1"><w:p><w:r><w:t>גלעד, ספרות הנבואה, עמ\' 12.</w:t></w:r></w:p></w:footnote>'
                 '<w:footnote w:id="2"><w:p><w:r><w:t>Pedersen, Israel, pp. 40-42.</w:t></w:r></w:p></w:footnote>'
                 '</w:footnotes>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("word/footnotes.xml", footnotes)


# --- classification and lookup ----------------------------------------------------------------------

def primo_fetch(calls):
    """Offline fake for fetch_url: Primo JSON, then the Alma CTO XML picked by the openurl title."""
    primo = (FIXTURES / "primo_pnxs.json").read_text(encoding="utf-8")
    cto = {"kotar-book": (FIXTURES / "cto_kotar.xml").read_text(encoding="utf-8"),
           "online-article": (FIXTURES / "cto_online.xml").read_text(encoding="utf-8")}

    def fetch(url):
        calls.append(url)
        if "pnxs" in url:
            return primo
        for title, xml in cto.items():
            if f"rft.title={title}" in url:
                return xml
        raise AssertionError(f"unexpected url {url}")
    return fetch


def test_classify_three_cases_from_recorded_shapes():
    calls = []
    hits = refs.propose("גלעד ספרות הנבואה", fetch=primo_fetch(calls))
    assert [h["suggested_status"] for h in hits] == ["kotar", "online", "print-only"]
    assert hits[2]["call_number"] == "BS1199 .P4 1962"
    assert any("svc_dat=CTO" in u for u in calls), "resolver must be asked for the CTO view"
    assert hits[1]["services"][0]["target_url"].endswith("x=2")


def test_classify_none_when_no_services_and_not_in_library():
    assert refs.classify([], "not_restricted", []) == (None, "")


def test_lookup_never_changes_status(tmp_path):
    reg = make_registry(tmp_path)
    write_refs(reg, "nevua", [ref("gilad-2011-aaaaaa", citation="גלעד")])
    result = refs.lookup_pending(reg, "nevua", fetch=primo_fetch([]))
    assert result[0]["key"] == "gilad-2011-aaaaaa" and len(result[0]["hits"]) == 3
    assert json.loads((reg / "refs" / "nevua.json").read_text(encoding="utf-8"))["refs"][0]["status"] == "pending"


# --- extract ----------------------------------------------------------------------------------------

def test_extract_counts_match_marker_hits_with_fake_pandoc(tmp_path):
    reg = make_registry(tmp_path)
    src = reg / "sources" / "nevua"
    src.mkdir(parents=True)
    (src / "lesson1.docx").write_bytes(b"not read: the runner is faked")
    candidates, report = refs.extract(reg, "nevua", runner=lambda path: PANDOC_MD)
    assert "sanity sources/nevua/lesson1.docx: 3 page-marker hits, 3 candidates proposed" in report
    assert len(candidates) == 3
    assert {c["found_in"] for c in candidates} == {"sources/nevua/lesson1.docx, footnote 1",
                                                   "sources/nevua/lesson1.docx, footnote 2",
                                                   "sources/nevua/lesson1.docx"}


def test_extract_real_pandoc_on_a_built_docx(tmp_path):
    if shutil.which("pandoc") is None:
        pytest.skip("pandoc not installed")
    reg = make_registry(tmp_path)
    src = reg / "sources" / "nevua"
    src.mkdir(parents=True)
    build_docx(src / "two-notes.docx")
    candidates, report = refs.extract(reg, "nevua")
    assert "sanity sources/nevua/two-notes.docx: 2 page-marker hits, 2 candidates proposed" in report
    assert [c["citation"] for c in candidates] == ["גלעד, ספרות הנבואה, עמ' 12.", "Pedersen, Israel, pp. 40-42."]


def test_extract_transcript_is_unverified(tmp_path):
    reg = make_registry(tmp_path)
    lesson = reg / "lessons" / "nevua" / "2026-10-01"
    lesson.mkdir(parents=True)
    (lesson / "transcript.txt").write_text((FIXTURES / "transcript_sample.txt").read_text(encoding="utf-8"), encoding="utf-8")
    candidates, report = refs.extract(reg, "nevua", runner=no_network)  # pandoc must not run on transcripts
    assert len(candidates) == 2
    assert all(c["found_in"].endswith("(transcript, unverified)") for c in candidates)
    assert "sanity lessons/nevua/2026-10-01/transcript.txt: 2 page-marker hits, 2 candidates proposed" in report


def test_extract_skips_pdf_without_failing(tmp_path):
    reg = make_registry(tmp_path)
    src = reg / "sources" / "nevua"
    src.mkdir(parents=True)
    (src / "scan.pdf").write_bytes(b"%PDF-1.4")
    candidates, report = refs.extract(reg, "nevua", runner=no_network)
    assert candidates == []
    assert report == ["skipped sources/nevua/scan.pdf: pandoc cannot read this type (PDF text is not extracted here)"]


def test_write_dedupes_and_never_overwrites_a_confirmed_status(tmp_path):
    reg = make_registry(tmp_path)
    citation ="ראו נבואה בעמ' 12 ועוד."
    key = refs.make_key(citation)
    write_refs(reg, "nevua", [ref(key, status="downloaded", citation=citation)])
    cand = [{"key": key, "citation": citation, "found_in": "x"},
            {"key": refs.make_key("new one, pp. 3"), "citation": "new one, pp. 3", "found_in": "y"},
            {"key": refs.make_key("new one, pp. 3"), "citation": "new one, pp. 3", "found_in": "y"}]
    assert refs.write_candidates(reg, "nevua", cand) == 1
    data = json.loads((reg / "refs" / "nevua.json").read_text(encoding="utf-8"))
    assert [r["status"] for r in data["refs"]] == ["downloaded", "pending"]
    assert data["_note"] == "keep me"


def test_write_creates_file_and_keys_are_deterministic(tmp_path):
    reg = make_registry(tmp_path)
    key = refs.make_key("Gilad, Prophecy, 2011, p. 3")
    assert key == refs.make_key("Gilad,  Prophecy, 2011, p. 3")  # whitespace does not change the key
    assert key.startswith("gilad-2011-") and len(key.rsplit("-", 1)[1]) == 6
    assert refs.make_key("ספרות בלבד, עמ' 3").startswith("ref-nd-")
    assert refs.write_candidates(reg, "nevua", [{"key": key, "citation": "c", "found_in": "f"}]) == 1
    assert json.loads((reg / "refs" / "nevua.json").read_text(encoding="utf-8"))["refs"][0]["key"] == key


# --- decisions, status, chores, index ---------------------------------------------------------------

def test_set_records_decision_and_keeps_unknown_fields(tmp_path):
    reg = make_registry(tmp_path)
    write_refs(reg, "nevua", [ref("a-2001-111111", custom="kept")])
    refs.record_decision(reg, "nevua", "a-2001-111111", "online", target_url="https://x.example.test", note="n")
    data = json.loads((reg / "refs" / "nevua.json").read_text(encoding="utf-8"))
    assert data["refs"][0] == {**ref("a-2001-111111", custom="kept"), "status": "online", "note": "n",
                               "target_url": "https://x.example.test"}
    assert data["_note"] == "keep me"


def test_set_validates_status_and_online_target_and_key(tmp_path):
    reg = make_registry(tmp_path)
    write_refs(reg, "nevua", [ref("a-2001-111111")])
    with pytest.raises(refs.RefsError, match="status must be one of"):
        refs.record_decision(reg, "nevua", "a-2001-111111", "maybe")
    with pytest.raises(refs.RefsError, match="needs --target-url"):
        refs.record_decision(reg, "nevua", "a-2001-111111", "online")
    with pytest.raises(refs.RefsError, match="no ref with key missing"):
        refs.record_decision(reg, "nevua", "missing", "not-found")


def test_status_exit_codes(tmp_path, capsys):
    reg = make_registry(tmp_path)
    assert refs.main(["--registry", str(reg), "status", "nevua"]) == 1  # no refs file yet
    write_refs(reg, "nevua", [ref("a-2001-111111")])
    assert refs.main(["--registry", str(reg), "status", "nevua"]) == 1  # one pending
    write_refs(reg, "nevua", [ref("a-2001-111111", status="downloaded")])
    assert refs.main(["--registry", str(reg), "status", "nevua"]) == 0
    assert "downloaded 1" in capsys.readouterr().out


def test_status_all_flags_source_course_without_refs(tmp_path):
    reg = make_registry(tmp_path)
    (reg / "sources" / "nevua").mkdir(parents=True)
    (reg / "sources" / "nevua" / "a.docx").write_bytes(b"x")
    assert refs.main(["--registry", str(reg), "status", "--all"]) == 1


def test_chores_plan_and_apply_skip_existing(tmp_path):
    reg = make_registry(tmp_path)
    write_refs(reg, "nevua", [
        ref("k-1", status="kotar", citation="kotar one"),
        ref("p-1", status="print-only", citation="print one", call_number="BS1199 .P4"),
        ref("n-1", status="not-found", citation="none one"),
        ref("o-1", status="online", citation="online one", target_url="https://x"),
    ])
    (reg / "chores.json").write_text(json.dumps([{"course": "nevua", "kind": "manual", "ref": "refs:nevua:n-1"}]),
                                     encoding="utf-8")
    plan = refs.chore_plan(reg, "nevua")
    assert [(p["kind"], p["ref"]) for p in plan] == [("kotar-source", "refs:nevua:k-1"), ("manual", "refs:nevua:p-1")]
    assert "BS1199 .P4" in plan[1]["text"]
    calls = []

    def runner(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stderr="")

    refs.apply_chores(reg, "nevua", plan, runner=runner)
    assert len(calls) == 2 and calls[0][1].endswith("courses.py") and "--kind" in calls[0]


def test_index_golden_output(tmp_path):
    data = {"course": "נבואה", "refs": [
        ref("a", status="ingested", citation="גלעד,  ספרות", role="quoted", found_in="lesson 1", trove_url="https://trove.example.test/p/3"),
        ref("b", status="print-only", citation="Pedersen", role="expansion", found_in="lesson 2"),
        ref("c", status="ingested", citation="Zimran", role="quoted", found_in="lesson 3"),
    ]}
    expected = (
        "# מקורות נזכרים: נבואה\n\n"
        "> Load this page when: a lesson or assignment cites one of these sources and you need its status or where it is.\n\n"
        "- גלעד, ספרות — role: quoted; status: ingested; cited in: lesson 1 — [Trove](https://trove.example.test/p/3)\n"
        "- Pedersen — role: expansion; status: print-only; cited in: lesson 2\n"
        "- Zimran — role: quoted; status: ingested; cited in: lesson 3 — Trove page not recorded\n"
    )
    assert refs.render_index("nevua", data) == expected


def test_no_network_for_offline_subcommands(tmp_path, capsys):
    reg = make_registry(tmp_path)
    write_refs(reg, "nevua", [ref("a-2001-111111", status="not-found", citation="x")])
    assert refs.main(["--registry", str(reg), "index", "nevua"]) == 0
    assert refs.main(["--registry", str(reg), "chores", "nevua"]) == 0
    assert refs.main(["--registry", str(reg), "status", "--all"]) == 0
    assert refs.main(["--registry", str(reg), "extract", "nevua"]) == 0
    assert refs.main(["--registry", str(reg), "lookup", "nevua", "--set", "a-2001-111111", "--status", "online",
                      "--target-url", "https://x.example.test"]) == 0


def test_cli_help_exits_zero():
    result = subprocess.run([sys.executable, "-I", str(ROOT / "src" / "scripts" / "courses" / "refs.py"), "--help"],
                            capture_output=True, text=True)
    assert result.returncode == 0 and "extract" in result.stdout and "index" in result.stdout


def test_lookup_network_failure_names_the_ref(tmp_path):
    reg = make_registry(tmp_path)
    write_refs(reg, "nevua", [ref("a-2001-111111", citation="x")])

    def down(url):
        raise OSError("connection refused")

    with pytest.raises(refs.RefsError, match="Primo lookup failed for a-2001-111111"):
        refs.lookup_pending(reg, "nevua", fetch=down)


def test_clean_markdown_unwraps_real_pandoc_noise():
    raw = ('[(הרוצים.ות [להרחיב]{.underline} יעיינו: י\' הופמן, תשע\\"א, עמ\' 23\\--26).]{dir="rtl"}'
           ' Warner (ed.), *The Bible*, pp. 51\\-64[).]{dir="rtl"} soft­hyphen')
    cleaned = refs.clean_markdown(raw)
    assert cleaned == ("(הרוצים.ות להרחיב יעיינו: י' הופמן, תשע\"א, עמ' 23--26). Warner (ed.), The Bible, pp. 51-64). "
                       "softhyphen")


def test_make_key_skips_editor_and_page_markers():
    assert refs.make_key("Warner (ed.), *The Bible*, 1990, pp. 51-64").startswith("warner-1990-")
    assert refs.make_key("pp. 3 in Zimran 2020").startswith("zimran-2020-")


def test_write_only_selects_and_rejects_unknown_keys(tmp_path):
    reg = make_registry(tmp_path)
    cand = [{"key": "a-2001-111111", "citation": "one", "found_in": "f"},
            {"key": "b-2002-222222", "citation": "two", "found_in": "f"}]
    with pytest.raises(refs.RefsError, match="not among the candidates: zzz"):
        refs.write_candidates(reg, "nevua", cand, only=["zzz"])
    assert refs.write_candidates(reg, "nevua", cand, only=["b-2002-222222"]) == 1
    assert [r["key"] for r in json.loads((reg / "refs" / "nevua.json").read_text(encoding="utf-8"))["refs"]] == ["b-2002-222222"]


def test_write_skips_exact_citation_already_recorded(tmp_path):
    reg = make_registry(tmp_path)
    write_refs(reg, "nevua", [ref("hand-made-key", citation="Zimran,  \"Multiple Facets\"")])
    cand = [{"key": "zimran-2020-abcdef", "citation": 'Zimran, "Multiple Facets"', "found_in": "f"}]
    assert refs.write_candidates(reg, "nevua", cand) == 0


def test_primo_query_keeps_author_and_title_words():
    citation = "Warner (ed.), *The Bible as Rhetoric: Studies in Biblical Persuasion*, London 1990, pp. 51-64"
    assert refs.primo_query(citation) == "Warner The Bible as Rhetoric"


def test_lookup_query_override_is_used(tmp_path):
    reg = make_registry(tmp_path)
    write_refs(reg, "nevua", [ref("a-2001-111111", citation="x")])
    seen = []

    def fetch(url):
        seen.append(url)
        return '{"docs": []}'

    refs.lookup_pending(reg, "nevua", fetch=fetch, query="custom words")
    assert "custom+words" in seen[0] or "custom%20words" in seen[0]
