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
    assert "replace(/-/g, ' ')" in js and "credentials: 'include'" in js
    with pytest.raises(ValueError):
        kf.tokens_js("1; alert(1)", 1, 2)


def test_size_check_rejects_placeholder():
    assert kf.is_real_page(_jpeg())
    assert not kf.is_real_page(_jpeg(6_000))
    assert not kf.is_real_page(b"<html>" + b"\0" * 30_000)


def test_fetch_names_pages_and_reports_failures(tmp_path):
    calls = []

    def getter(url):
        calls.append(url)
        return _jpeg(6_000) if U2 in url else _jpeg()

    result = kf.fetch(tmp_path, [U1, U2], first_page=307, getter=getter, retries=1)
    assert [p["file"] for p in result["pages"]] == ["p0307.jpg"]
    assert result["failed"] == [{"page": 308, "token": U2, "bytes": 6_000}]
    assert len(calls) == 3  # U2 retried once
    assert "nStep=9" in calls[0] and "gPageToken=" + U1 in calls[0]
    assert json.loads((tmp_path / "manifest.json").read_text())["first_page"] == 307


def test_ordered_pages_sorts_numerically(tmp_path):
    for name in ["p1000.jpg", "p0099.jpg", "p0307.jpg", "notes.txt", "manifest.json"]:
        (tmp_path / name).write_bytes(b"x")
    assert [p.name for p in kf.ordered_pages(tmp_path)] == ["p0099.jpg", "p0307.jpg", "p1000.jpg"]


def test_merge_writes_pdf_in_page_order(tmp_path):
    from PIL import Image

    for page, colour in [(309, "blue"), (307, "red"), (308, "green")]:
        Image.new("RGB", (20, 30), colour).save(tmp_path / kf.page_name(page), "JPEG")
    out = tmp_path / "out" / "x.pdf"
    assert kf.merge(tmp_path, out) == 3
    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page\b(?!s)", data)) == 3
    # Pages keep printed order: red (307), green (308), blue (309).
    streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S)
    colours = [Image.open(io.BytesIO(s)).convert("RGB").getpixel((10, 15)) for s in streams if s[:3] == b"\xff\xd8\xff"]
    assert [max(range(3), key=lambda i: c[i]) for c in colours] == [0, 1, 2]


def test_offset_cli(capsys):
    assert kf.main(["offset", "315", "303", "--pages", "307-324"]) == 0
    assert json.loads(capsys.readouterr().out) == {"offset": 12, "start_idx": 319, "end_idx": 336}
