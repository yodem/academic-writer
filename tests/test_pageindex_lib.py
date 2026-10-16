"""pilib, the library tool: the read side (JSON shapes that `aw library` parses), packaging and pins.

No PageIndex, litellm or network is needed. The read-side shapes are compared with literal expected text, so an
older pilib on a server and this one stay interchangeable for `aw`.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "pageindex"))
from helpers import PKG, REPO, run_main  # noqa: E402

from pilib import library as lib  # noqa: E402

PYTHON_FILES = sorted(p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts)


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "library"
    monkeypatch.setenv("AW_LIBRARY", str(root))
    return root


def seed_book(book_id="b1", pages=None, structure=None, extra_meta=None, pagemap=None):
    """A book as the original pilib wrote it."""
    pages = pages or ["page one", "page two  \n", "עמוד שלוש", "page four"]
    structure = structure or [
        {"node_id": "0000", "title": "Intro", "start_index": 1, "end_index": 2, "summary": " short summary ",
         "nodes": [{"node_id": "0001", "title": "Sub", "start_index": 2, "end_index": 2, "prefix_summary": "pre"}]},
        {"node_id": "0002", "title": "Ending", "start_index": 3, "end_index": 4}]
    d = lib.book_dir(book_id)
    lib.write_json(d / "pages.json", pages)
    lib.write_json(d / "tree.json", {"book_id": book_id, "title": "A Title", "author": "Au", "n_pages": len(pages),
                                     "toc_source": "trove-toc", "structure": structure})
    meta = {"book_id": book_id, "title": "A Title", "author": "Au",
            "origin": {"trove": {"trove_id": "tid1", "title": "A Title"}}, "indexer": {"llm_calls": 0},
            "n_pages": len(pages)}
    meta.update(extra_meta or {})
    lib.write_json(d / "meta.json", meta)
    if pagemap:
        lib.write_json(d / "pagemap.json", {"trove_id": "tid1", "pdf_to_trove": pagemap})
    lib.rebuild_catalog()
    return d


# ----------------------------------------------------------------------------- packaging

@pytest.mark.parametrize("path", PYTHON_FILES, ids=lambda p: str(p.relative_to(PKG)))
def test_every_file_parses_as_python_39(path):
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 9))


def test_no_cloud_code_in_the_package():
    for path in PYTHON_FILES:
        text = path.read_text(encoding="utf-8")
        assert "cloud" not in text.lower(), f"{path.name} mentions the hosted service"
        assert "PAGEINDEX_API_KEY" not in text, path.name
    assert not (PKG / "pilib" / "cloud.py").exists()


def test_help_runs_without_any_dependency():
    env = {**os.environ, "PYTHONPATH": str(PKG)}
    proc = subprocess.run([sys.executable, "-m", "pilib", "--help"], capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    for name in ("health", "index-trove", "index-md", "index-pdf", "export-trove", "list", "catalog", "tree", "read",
                 "meta", "verify-library"):
        assert name in proc.stdout


def test_importing_the_commands_pulls_in_no_heavy_dependency():
    code = ("import sys, pilib.__main__, pilib.native, pilib.structure, pilib.summarize, pilib.index, pilib.library\n"
            "heavy = [m for m in ('litellm', 'pageindex', 'weasyprint', 'PyPDF2', 'reportlab') if m in sys.modules]\n"
            "print(heavy)\nsys.exit(1 if heavy else 0)\n")
    env = {**os.environ, "PYTHONPATH": str(PKG)}
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ----------------------------------------------------------------------------- read side, byte-compatible shapes

def test_read_json_shape_is_byte_compatible(library, capsys):
    seed_book()
    code, out, _ = run_main(["read", "b1", "2,3", "--json"], capsys)
    assert code == 0
    assert out == ('{"book_id": "b1", "pages": [{"page": 2, "content": "page two"}, '
                   '{"page": 3, "content": "עמוד שלוש"}]}\n')
    code, out, _ = run_main(["read", "b1", "all", "--json"], capsys)
    assert json.loads(out)["pages"][-1] == {"page": 4, "content": "page four"}
    assert len(json.loads(out)["pages"]) == 4


def test_read_plain_banner_and_page_cap(library, capsys):
    seed_book()
    code, out, _ = run_main(["read", "b1", "1-2"], capsys)
    assert code == 0 and out == "── Page 1 ──\npage one\n── Page 2 ──\npage two\n"
    seed_book("big", pages=[f"p{i}" for i in range(1, 13)])
    code, _, err = run_main(["read", "big", "1-12"], capsys)
    assert code == 1 and "at most 10 per read" in err
    code, _, err = run_main(["read", "b1", "40"], capsys)
    assert code == 1 and "no pages in range" in err


def test_meta_shape_is_byte_compatible(library, capsys):
    seed_book()
    code, out, _ = run_main(["meta", "b1"], capsys)
    assert code == 0
    assert out == ('{"book_id": "b1", "title": "A Title", "n_pages": 4, "origin": {"trove": {"trove_id": "tid1", '
                   '"title": "A Title"}}, "trove_id": "tid1", "pagemap": null}\n')
    seed_book("b2", pagemap=[1, 1, 2, 3])
    code, out, _ = run_main(["meta", "b2"], capsys)
    assert json.loads(out)["pagemap"] == [1, 1, 2, 3]
    code, _, err = run_main(["meta", "nope"], capsys)
    assert code == 1 and "book not indexed: nope" in err


def test_tree_shape_depth_node_and_summaries(library, capsys):
    seed_book()
    code, out, _ = run_main(["tree", "b1"], capsys)
    assert code == 0
    tree = json.loads(out)
    assert list(tree) == ["book_id", "title", "n_pages", "structure"]
    first = tree["structure"][0]
    assert list(first) == ["node_id", "title", "start_index", "end_index", "summary", "nodes"]
    assert first["summary"] == "short summary"
    assert first["nodes"][0]["summary"] == "pre"  # a parent's prefix_summary is shown as summary
    assert "summary" not in tree["structure"][1]
    _, out, _ = run_main(["tree", "b1", "--depth", "1"], capsys)
    cut = json.loads(out)["structure"][0]
    assert "nodes" not in cut and cut["children_hidden"] == 1
    _, out, _ = run_main(["tree", "b1", "--node", "0002"], capsys)
    assert [n["node_id"] for n in json.loads(out)["structure"]] == ["0002"]
    code, _, err = run_main(["tree", "b1", "--node", "9999"], capsys)
    assert code == 1 and "no node '9999'" in err


def test_tree_of_a_large_book_is_cut_with_a_note(library, capsys):
    nodes = [{"node_id": f"{i:04d}", "title": "T" * 300, "start_index": 1, "end_index": 1,
              "nodes": [{"node_id": f"c{i:04d}", "title": "C" * 300, "start_index": 1, "end_index": 1}]}
             for i in range(160)]
    seed_book("large", structure=nodes)
    _, out, _ = run_main(["tree", "large", "--max-title", "400"], capsys)
    tree = json.loads(out)
    assert "note" in tree and "children_hidden" in tree["structure"][0]


def test_catalog_list_and_shelf(library, capsys):
    seed_book("b1")
    seed_book("b2")
    _, out, _ = run_main(["catalog"], capsys)
    assert out == json.dumps(lib.catalog()["books"], ensure_ascii=False, indent=1) + "\n"
    shelf = library.parent / "shelf.json"
    shelf.write_text(json.dumps({"books": ["b2"]}))
    _, out, _ = run_main(["catalog", "--shelf", str(shelf)], capsys)
    assert list(json.loads(out)) == ["b2"]
    _, out, _ = run_main(["list"], capsys)
    assert out == "b1\t4 pp\ttrove-toc\tA Title\nb2\t4 pp\ttrove-toc\tA Title\n"


def test_verify_library(library, capsys):
    seed_book("good")
    code, out, _ = run_main(["verify-library", "--min-books", "1"], capsys)
    assert code == 0 and "ok good: 4 pages, 3 nodes, toc_source=trove-toc" in out
    code, _, err = run_main(["verify-library", "--min-books", "1", "--no-summary"], capsys)
    assert code == 1 and "nodes carry LLM summaries" in err
    code, _, err = run_main(["verify-library", "--require-summary"], capsys)
    assert code == 1 and "carry a summary (< 80%)" in err
    seed_book("bad", structure=[{"node_id": "0000", "title": "X", "start_index": 3, "end_index": 9}])
    code, _, err = run_main(["verify-library"], capsys)
    assert code == 1 and "bad page ranges" in err
    code, _, err = run_main(["verify-library", "--min-books", "5"], capsys)
    assert code == 1 and "valid books (< 5)" in err


def test_a_bad_book_id_is_refused():
    with pytest.raises(ValueError):
        lib.book_dir("../x")
    assert lib.parse_ranges("5-7,12,all", 3) == [1, 2, 3]
    assert lib.parse_ranges("7-5", 10) == [5, 6, 7]


# ----------------------------------------------------------------------------- health

def test_health_reports_the_tier(library, capsys, monkeypatch):
    import pilib.__main__ as cli
    monkeypatch.setattr(cli, "probe", lambda name: None)
    monkeypatch.setattr(cli, "distribution_version", lambda name: None)
    code, out, _ = run_main(["health"], capsys)
    info = json.loads(out)
    assert code == 0 and info["ok"] is True and info["tier"] == "read"
    assert {"pilib_version", "python", "tier", "pageindex_commit", "litellm", "pageindex", "weasyprint", "library",
            "books"} <= set(info)
    code, out, _ = run_main(["health", "--require", "core"], capsys)
    assert code == 1 and json.loads(out)["ok"] is False
    monkeypatch.setattr(cli, "distribution_version", lambda name: "1.83.9" if name == "litellm" else None)
    monkeypatch.setattr(cli, "probe", lambda name: object() if name == "litellm" else None)
    code, out, _ = run_main(["health", "--require", "core"], capsys)
    info = json.loads(out)
    assert code == 0 and info["tier"] == "core" and info["litellm"] == "1.83.9"
    code, out, _ = run_main(["health", "--require", "structure"], capsys)
    assert code == 1
    monkeypatch.setattr(cli, "probe", lambda name: object())
    code, out, _ = run_main(["health", "--require", "structure"], capsys)
    info = json.loads(out)
    assert code == 0 and info["tier"] == "structure" and info["pageindex_commit"].startswith("af92d96")


# ----------------------------------------------------------------------------- pins and shipped files

PINNED = json.loads((PKG / "PINNED.json").read_text(encoding="utf-8"))
THRESHOLDS = json.loads((REPO / "src" / "thresholds.json").read_text(encoding="utf-8"))["library"]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_pinned_json_matches_the_files_and_thresholds():
    assert PINNED["pilib_version"] == __import__("pilib").__version__
    assert PINNED["pageindex"]["commit"] == THRESHOLDS["install"]["pageindexCommit"]
    assert re.fullmatch(r"[0-9a-f]{64}", PINNED["pageindex"]["tarball_sha256"])
    assert PINNED["pageindex"]["commit"] in PINNED["pageindex"]["tarball_url"]
    for tier in ("core", "structure"):
        info = PINNED["tiers"][tier]
        assert info["requirements_sha256"] == sha256(PKG / info["requirements"]), f"{tier} requirements changed without PINNED.json"
        assert re.search(rf"^litellm=={re.escape(info['litellm'])} ", (PKG / info["requirements"]).read_text(), re.M)
    assert re.search(rf"^weasyprint=={re.escape(PINNED['tiers']['structure']['weasyprint'])} ", (PKG / "requirements-structure.txt").read_text(), re.M)
    assert PINNED["tiers"]["structure"]["system_libraries"]["macos"] == "brew install pango"
    assert PINNED["tiers"]["core"]["requires_python"] == ">=" + THRESHOLDS["install"]["minPythonCore"]
    assert PINNED["tiers"]["structure"]["requires_python"] == ">=" + THRESHOLDS["install"]["minPython"]
    # litellm 1.105 needs Python 3.10, so the 3.9 tier is older than the structure tier
    assert PINNED["tiers"]["core"]["litellm"] != PINNED["tiers"]["structure"]["litellm"]


def test_requirements_are_fully_hashed():
    for name in ("requirements-core.txt", "requirements-structure.txt"):
        text = (PKG / name).read_text(encoding="utf-8")
        blocks = re.findall(r"^(\S+(?: @ \S+)?) \\\n((?:    --hash=sha256:[0-9a-f]{64}(?: \\)?\n)+)", text, re.M)
        requirements = [line for line in text.splitlines() if re.match(r"^[A-Za-z0-9_.\-\[\]]+( @ \S+|==\S+) \\$", line)]
        assert requirements and len(blocks) == len(requirements), f"{name}: every requirement needs a hash"
        assert not re.search(r"^(-e |--index-url|--extra-index-url|git\+|\.|/)", text, re.M)


def test_structure_requirements_pin_the_pageindex_tarball():
    structure = (PKG / "requirements-structure.txt").read_text(encoding="utf-8")
    pin = PINNED["pageindex"]
    assert f"pageindex @ {pin['tarball_url']} \\\n    --hash=sha256:{pin['tarball_sha256']}" in structure
    assert "pageindex @" not in (PKG / "requirements-core.txt").read_text(encoding="utf-8")


def test_index_defaults_equal_the_thresholds():
    from pilib.config import INDEX_DEFAULTS, index_settings
    block = THRESHOLDS["index"]
    assert {k: block[k] for k in INDEX_DEFAULTS} == INDEX_DEFAULTS
    from pilib.config import THRESHOLDS as FOUND
    assert FOUND.resolve() == (REPO / "src" / "thresholds.json").resolve()  # two folders above the package, as in the built plugin
    assert index_settings() == INDEX_DEFAULTS


def test_notices_name_the_third_party_projects():
    text = (PKG / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for needle in ("PageIndex", "Vectify AI", "MIT", "LiteLLM", "PyPDF2", "pypdfium2", "WeasyPrint", PINNED["pageindex"]["commit"]):
        assert needle in text
