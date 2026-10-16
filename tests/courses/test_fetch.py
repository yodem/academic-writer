import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "scripts" / "courses"))
import chores
import courses
import refs


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(refs, "fetch_url", boom)
    monkeypatch.setattr(refs.urllib.request, "urlopen", boom)
    monkeypatch.setattr(refs.subprocess, "run", boom)
    monkeypatch.delenv("ANNAS_ARCHIVE_KEY", raising=False)


def reg_with(tmp_path, ref):
    d = tmp_path / "reg"
    (d / "refs").mkdir(parents=True)
    (d / "term.json").write_text(json.dumps({"term": "T"}), encoding="utf-8")
    (d / "nevua.json").write_text(json.dumps({"slug": "nevua", "name": "נבואה"}), encoding="utf-8")
    (d / "refs" / "nevua.json").write_text(json.dumps({"course": "nevua", "_note": "n", "refs": [ref]}, ensure_ascii=False), encoding="utf-8")
    return d


def stored(d):
    return json.loads((d / "refs" / "nevua.json").read_text())["refs"][0]


def hit(status, **kw):
    return {"title": "T", "suggested_status": status, "services": kw.get("services", []), "call_number": kw.get("call", "")}


def steps(result):
    return {e["step"]: e["outcome"] for e in result["log"]}


def test_no_annas_key_records_not_checked_and_continues(tmp_path):
    d = reg_with(tmp_path, {"key": "k", "citation": "Smith Book 1999", "status": "pending"})
    out = refs.fetch_ref(d, "nevua", "k", env={}, lookup=lambda c: [hit("print-only", call="123.4")],
                         annas=lambda c: pytest.fail("annas must not run without a key"))
    s = steps(out)
    assert s["annas"] == "not-checked" and s["lookup"] == "print-only" and s["print-only"] == "print-only"
    ref = stored(d)
    assert ref["annas"] == "not-checked" and ref["status"] == "print-only" and ref["call_number"] == "123.4"
    assert [e["step"] for e in ref["fetch_log"]] == ["annas", "lookup", "print-only"]
    assert all({"step", "outcome", "at"} <= set(e) for e in ref["fetch_log"])


def test_annas_error_is_recorded_and_chain_continues(tmp_path):
    d = reg_with(tmp_path, {"key": "k", "citation": "Smith Book 1999", "status": "pending"})
    def broken(c):
        raise refs.RefsError("DDoS-Guard 403")
    out = refs.fetch_ref(d, "nevua", "k", env={"ANNAS_ARCHIVE_KEY": "x"}, lookup=lambda c: [hit("print-only")], annas=broken)
    assert steps(out)["annas"] == "error" and stored(d)["annas"] == "error" and stored(d)["status"] == "print-only"


def test_annas_candidates_keep_definitive_value(tmp_path):
    d = reg_with(tmp_path, {"key": "k", "citation": "Smith Book 1999", "status": "print-only", "annas": "found-used"})
    refs.fetch_ref(d, "nevua", "k", env={"ANNAS_ARCHIVE_KEY": "x"}, annas=lambda c: [{"md5": "m"}])
    assert stored(d)["annas"] == "found-used"


def test_online_download_enqueues_ocr_per_policy(tmp_path):
    pdf = tmp_path / "k.pdf"
    pdf.write_bytes(b"%PDF")
    d = reg_with(tmp_path, {"key": "k", "citation": "Smith Book 1999", "status": "pending"})
    svc = [{"package": "JSTOR", "target_url": "https://x/y", "type": "", "free": ""}]
    out = refs.fetch_ref(d, "nevua", "k", env={}, file=pdf, lookup=lambda c: [hit("online", services=svc)])
    ref = stored(d)
    assert ref["status"] == "downloaded" and ref["download_path"] == str(pdf) and ref["target_url"] == "https://x/y"
    assert ref["ocr_next"]["state"] == "queued" and ref["ocr_next"]["policy"][0] == "gemini-text-first"
    assert "empty-gemini-page-blocked" in ref["ocr_next"]["policy"]
    assert steps(out)["ocr"] == "queued"
    again = refs.fetch_ref(d, "nevua", "k", env={})  # resume: no second queue entry
    assert steps(again)["ocr"] == "skipped"


def test_online_without_file_needs_browser_download(tmp_path, monkeypatch):
    monkeypatch.setattr(refs.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    d = reg_with(tmp_path, {"key": "k", "citation": "c", "status": "online", "target_url": "https://x"})
    out = refs.fetch_ref(d, "nevua", "k", env={})
    assert steps(out)["download"] == "needs-browser-download" and stored(d)["status"] == "online"


def test_lookup_kotar_discards_annas_candidates(tmp_path):
    d = reg_with(tmp_path, {"key": "k", "citation": "גלעד ספרות", "status": "pending"})
    out = refs.fetch_ref(d, "nevua", "k", env={"ANNAS_ARCHIVE_KEY": "x"}, lookup=lambda c: [hit("kotar")],
                         annas=lambda c: [{"md5": "m"}])
    ref = stored(d)
    assert ref["status"] == "kotar" and ref["annas"] == "not-checked" and "annas_candidates" not in ref
    assert steps(out)["annas"] == "discarded-kotar" and steps(out)["kotar"] == "chore-created"


def test_annas_error_keeps_recorded_not_found(tmp_path):
    d = reg_with(tmp_path, {"key": "k", "citation": "c", "status": "print-only", "annas": "not-found"})
    def broken(c):
        raise refs.RefsError("403")
    refs.fetch_ref(d, "nevua", "k", env={"ANNAS_ARCHIVE_KEY": "x"}, annas=broken)
    assert stored(d)["annas"] == "not-found"


def test_kotar_known_status_skips_annas_and_adds_chore(tmp_path):
    d = reg_with(tmp_path, {"key": "k", "citation": "גלעד ספרות", "status": "kotar"})
    out = refs.fetch_ref(d, "nevua", "k", env={"ANNAS_ARCHIVE_KEY": "x"}, annas=lambda c: pytest.fail("no annas for kotar"))
    assert steps(out)["annas"] == "skipped-kotar" and steps(out)["kotar"] == "chore-created"
    cs = chores.load(courses.Registry(d))
    assert len(cs) == 1 and cs[0]["kind"] == "kotar-source" and "kotar-fetch" in cs[0]["text"]
    refs.fetch_ref(d, "nevua", "k", env={})
    assert len(chores.load(courses.Registry(d))) == 1


def test_multiple_hits_need_a_choice_then_hit_flag(tmp_path):
    d = reg_with(tmp_path, {"key": "k", "citation": "c", "status": "pending"})
    hits = [hit("print-only", call="1"), hit("print-only", call="2")]
    out = refs.fetch_ref(d, "nevua", "k", env={}, lookup=lambda c: hits)
    assert steps(out)["lookup"] == "needs-choice" and stored(d)["status"] == "pending"
    refs.fetch_ref(d, "nevua", "k", env={}, lookup=lambda c: hits, hit=1)
    assert stored(d)["call_number"] == "2"


def test_dry_run_writes_nothing_and_task_flag_links(tmp_path):
    d = reg_with(tmp_path, {"key": "k", "citation": "c", "status": "pending"})
    before = (d / "refs" / "nevua.json").read_text()
    out = refs.fetch_ref(d, "nevua", "k", env={}, dry_run=True, lookup=lambda c: [hit("print-only")])
    assert out["status"] == "print-only" and (d / "refs" / "nevua.json").read_text() == before
    chore = chores.add_chore(courses.Registry(d), course="nevua", kind="assignment", ref="9", title="מטלה")
    refs.fetch_ref(d, "nevua", "k", env={}, task=chore["id"], lookup=lambda c: [hit("print-only")])
    assert stored(d)["tasks"] == [chore["id"]]


def test_unknown_ref_and_cli(tmp_path, monkeypatch, capsys):
    d = reg_with(tmp_path, {"key": "k", "citation": "c", "status": "not-found"})
    with pytest.raises(refs.RefsError):
        refs.fetch_ref(d, "nevua", "zzz", env={})
    assert refs.main(["--registry", str(d), "fetch", "--course", "nevua", "--ref", "k", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "not-found"
