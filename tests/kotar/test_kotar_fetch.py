import io
import re
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "scripts" / "kotar"))
import kotar_fetch as kf  # noqa: E402

U1 = "0f8fad5b-d9cb-469f-a165-70867728950e"
U2 = "7c9e6679-7425-40de-944b-e07fc1f90ae7"


def _jpeg(size=30_000):
    return b"\xff\xd8\xff" + b"\0" * (size - 3)


def test_parse_tokens_accepts_spaces_and_dashes_in_order():
    text = "2 tokens\n" + U2.replace("-", " ") + "\n" + U1.upper() + "\n" + U2
    assert kf.parse_tokens(text) == [U2, U1]


def test_parse_tokens_ignores_noise():
    assert kf.parse_tokens("nothing here 1234 abcd") == []


def test_batches_cap_at_ten():
    assert kf.batches(315, 336) == [(315, 324), (325, 334), (335, 336)]
    with pytest.raises(ValueError):
        kf.batches(5, 4)


def test_tokens_js_has_book_and_ranges_and_no_dashes_out():
    js = kf.tokens_js("95229718", 319, 336)
    assert "nBookID=95229718" in js and "[[319, 328], [329, 336]]" in js
    assert js.startswith("await (async () => {")
    assert "replace(/-/g, ' ')" in js and "credentials: 'include'" in js
    with pytest.raises(ValueError):
        kf.tokens_js("1; alert(1)", 1, 2)


def test_size_check_rejects_placeholder():
    assert kf.is_real_page(_jpeg())
    assert not kf.is_real_page(_jpeg(6_000))
    assert not kf.is_real_page(b"<html>" + b"\0" * 30_000)


def _tok(i):
    return f"{i:08x}-0000-4000-8000-{i:012x}"


def _real_jpeg():
    import os
    from PIL import Image

    buf = io.BytesIO()
    Image.frombytes("RGB", (160, 160), os.urandom(160 * 160 * 3)).save(buf, "JPEG", quality=95)
    assert kf.is_real_page(buf.getvalue())
    return buf.getvalue()


def _fetch(out, start_idx, n, first_page, step=1, last_page=None):
    page = _real_jpeg()
    return kf.fetch(out, [_tok(start_idx + i) for i in range(n)], start_idx, first_page, step,
                    last_page, getter=lambda url: page)


def test_fetch_names_by_index_and_reports_failures(tmp_path):
    calls = []

    def getter(url):
        calls.append(url)
        return _jpeg(6_000) if U2 in url else _jpeg()

    result = kf.fetch(tmp_path, [U1, U2], start_idx=319, first_page=307, getter=getter, retries=1)
    assert sorted(p["file"] for p in result["pages"].values()) == ["i0319.jpg"]
    assert result["failed"] == [{"idx": 320, "token": U2, "bytes": 6_000}]
    assert len(calls) == 3  # U2 retried once
    assert "nStep=9" in calls[0] and "gPageToken=" + U1 in calls[0]
    seg = json.loads((tmp_path / "manifest.json").read_text())["segments"][0]
    assert seg["first_page"] == 307 and seg["batches"] == [[319, 320]]


def test_check_requires_first_and_last_of_every_batch(tmp_path):
    _fetch(tmp_path, 319, 18, 307)  # batches 319-328, 329-336
    result = kf.check(tmp_path, {"319": 307, "328": 316, "329": 317})
    assert not result["verified"]
    assert [p["idx"] for p in result["problems"]] == [336]  # never assumed
    with pytest.raises(SystemExit):
        kf.merge(tmp_path, tmp_path / "x.pdf")
    assert kf.check(tmp_path, {"336": 324})["verified"]


def test_plate_inside_batch_fails_until_reprobed(tmp_path):
    # Encyclopedia vol. 4: two columns per page, an unnumbered plate at index 330.
    _fetch(tmp_path, 326, 10, 559, step=2)
    result = kf.check(tmp_path, {"326": 559, "335": 575})
    assert not result["verified"]
    bad = result["problems"][0]
    assert (bad["idx"], bad["expected"], bad["seen"]) == (335, 577, 575)
    assert "re-probe" in bad["fix"]
    assert kf.check(tmp_path, plates=[330])["verified"]


def test_plate_seen_at_batch_end_is_a_mismatch_not_a_correction(tmp_path):
    # The real case: indices 335-338 were plates, so pp. 577-579 sat at 339-340.
    _fetch(tmp_path, 326, 11, 559, step=2, last_page=579)  # batches 326-335, 336-336
    result = kf.check(tmp_path, {"326": 559, "335": "plate", "336": "plate"})
    assert not result["verified"]
    assert {p["idx"] for p in result["problems"]} == {335, 336}
    result = kf.check(tmp_path, plates=[335, 336])
    assert not result["problems"] and result["short"][0]["covers_to"] == 575  # still short of 579
    _fetch(tmp_path, 337, 4, 577, step=2, last_page=579)  # new segment after the re-probe
    result = kf.check(tmp_path, {"337": "plate", "340": 579})
    assert {p["idx"] for p in result["problems"]} == {337, 340}  # 340 expected 583 until plates are declared
    assert kf.check(tmp_path, plates=[337, 338])["verified"]
    out = tmp_path / "x.pdf"
    assert kf.merge(tmp_path, out) == 15


def test_refetch_clears_verified(tmp_path):
    _fetch(tmp_path, 10, 1, 1)
    assert kf.check(tmp_path, {"10": 1})["verified"]
    _fetch(tmp_path, 11, 1, 2)
    assert not kf.load_manifest(tmp_path)["verified"]


def test_parse_seen():
    assert kf.parse_seen(["319:307", "335:Plate"]) == {"319": 307, "335": "plate"}
    with pytest.raises(ValueError):
        kf.parse_seen(["319=307"])


def test_ordered_pages_sorts_by_index(tmp_path):
    for name in ["i1000.jpg", "i0099.jpg", "i0307.jpg", "notes.txt", "manifest.json", "peek.png"]:
        (tmp_path / name).write_bytes(b"x")
    assert [p.name for p in kf.ordered_pages(tmp_path)] == ["i0099.jpg", "i0307.jpg", "i1000.jpg"]


def test_merge_writes_pdf_in_index_order(tmp_path):
    from PIL import Image

    for idx, colour in [(309, "blue"), (307, "red"), (308, "green")]:
        Image.new("RGB", (20, 30), colour).save(tmp_path / kf.page_name(idx), "JPEG")
    kf.save_manifest(tmp_path, {**kf.load_manifest(tmp_path), "verified": True})
    out = tmp_path / "out" / "x.pdf"
    assert kf.merge(tmp_path, out) == 3
    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page\b(?!s)", data)) == 3
    # Pages keep index order: red (307), green (308), blue (309).
    streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S)
    colours = [Image.open(io.BytesIO(s)).convert("RGB").getpixel((10, 15)) for s in streams if s[:3] == b"\xff\xd8\xff"]
    assert [max(range(3), key=lambda i: c[i]) for c in colours] == [0, 1, 2]


def test_peek_writes_strip_sheet(tmp_path):
    from PIL import Image

    _fetch(tmp_path, 1, 2, 1)
    for idx in (1, 2):
        Image.new("RGB", (100, 140), "white").save(tmp_path / kf.page_name(idx), "JPEG")
    sheet = Image.open(kf.peek(tmp_path))
    assert sheet.size[0] == 50 and sheet.size[1] > 0


def test_offset_cli(capsys):
    assert kf.main(["offset", "315", "303", "--pages", "307-324"]) == 0
    assert json.loads(capsys.readouterr().out) == {"offset": 12, "start_idx": 319, "end_idx": 336}
