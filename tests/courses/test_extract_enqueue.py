import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "scripts" / "courses"))
import extract


def _reg(tmp_path):
    reg = tmp_path / "term"
    (reg / "refs").mkdir(parents=True)
    pdf = tmp_path / "a.pdf"; pdf.write_bytes(b"%PDF-1.4")
    audio = tmp_path / "l.m4a"; audio.write_bytes(b"x")
    done = tmp_path / "d.pdf"; done.write_bytes(b"%PDF-1.4")
    ref_pdf = tmp_path / "r.pdf"; ref_pdf.write_bytes(b"%PDF-1.4")
    (reg / "cohen.json").write_text(json.dumps({"slug": "cohen", "sources": [
        {"sha8": "aaaaaaaa", "file": str(pdf), "status": "drive_done"},
        {"sha8": "bbbbbbbb", "file": str(audio), "kind": "media"},
        {"sha8": "cccccccc", "file": str(done), "status": "done", "trove": {"book_id": "B", "page": 4}},
        {"sha8": "dddddddd", "file": str(tmp_path / "missing.pdf")},
    ]}))
    (reg / "cohen.json.bak-1").write_text("{}")
    (reg / "term.json").write_text(json.dumps({"term": "t"}))
    (reg / "refs" / "cohen.json").write_text(json.dumps({"refs": [{"key": "k1", "download_path": str(ref_pdf)}, {"key": "k2"}]}))
    return reg


def test_enqueue_queues_every_unextracted_text_once(tmp_path):
    reg = _reg(tmp_path)
    report = extract.enqueue_all(reg)
    assert [j["course"] for j in report["jobs"]] == ["cohen"]
    assert report["jobs"][0]["items"] == [{"kind": "source", "key": "aaaaaaaa"}, {"kind": "ref", "key": "k1"}]
    jobs = list((reg / "queue" / "extract").glob("*.json"))
    assert len(jobs) == 1
    job = json.loads(jobs[0].read_text())
    assert all(i["method"] == "auto" for i in job["items"]) and job["origin"] == "nightly"
    assert extract.enqueue_all(reg)["jobs"] == []  # already queued: a second night does not queue it again


def test_enqueue_skips_extracted_and_dry_run_writes_nothing(tmp_path):
    reg = _reg(tmp_path)
    out = extract.extracted_path(reg, "cohen", "source", "aaaaaaaa")
    out.parent.mkdir(parents=True); out.write_text("text")
    report = extract.enqueue_all(reg, dry_run=True)
    assert report["jobs"][0]["items"] == [{"kind": "ref", "key": "k1"}]
    assert not (reg / "queue" / "extract").exists()


def test_enqueue_skips_items_already_handed_off(tmp_path):
    reg = _reg(tmp_path)
    hand = reg / "queue" / "extract" / "handoff"; hand.mkdir(parents=True)
    (hand / "cohen-source-aaaaaaaa.json").write_text(json.dumps({"course": "cohen", "kind": "source", "key": "aaaaaaaa"}))
    assert extract.enqueue_all(reg, dry_run=True)["jobs"][0]["items"] == [{"kind": "ref", "key": "k1"}]
