"""pilib index-trove / index-md: the native tree from the hinted table of contents, summaries, reuse, caps, fallback.

A fake `trove` command serves fixture books, a stub `litellm` answers model calls, and PageIndex is stubbed in
sys.modules, so nothing here needs the network, a model, PageIndex or WeasyPrint.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "pageindex"))
from helpers import (BOOKS, PKG, fixture_json, fixture_pages, install_fake_trove, install_litellm,  # noqa: E402
                     run_json, run_main)

from pilib import library as lib  # noqa: E402
from pilib import native, summarize  # noqa: E402

CONTRACT = (Path(__file__).resolve().parent / "fixtures" / "pageindex" / "contract.md").read_text(encoding="utf-8")
HINTED = "hinted-demo"
NODES = 7  # 5 leaves + 2 parents in the hinted fixture

SUCCESS_KEYS = {"ok", "command", "dry_run", "book_id", "trove_id", "title", "source", "fallback", "summaries", "model",
                "n_pages", "toc_entries", "hinted_entries", "nodes", "nodes_with_summary", "summaries_reused",
                "summaries_generated", "summary_failures", "expected_calls", "input_chars", "calls", "failures",
                "prompt_tokens", "completion_tokens", "reasoning_tokens", "cost_usd", "cost_unknown_calls", "call_cap",
                "seconds", "library", "indexed_at", "warnings"}
FAILURE_KEYS = {"ok", "command", "code", "error"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("AW_LIBRARY", str(tmp_path / "library"))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(summarize, "RETRY_PAUSE", 0)
    data, log = install_fake_trove(tmp_path, monkeypatch)
    stub = install_litellm(monkeypatch)
    return types.SimpleNamespace(tmp=tmp_path, data=data, log=log, stub=stub, library=tmp_path / "library")


def index(capsys, *extra, book=HINTED):
    return run_json(["index-trove", book, "--concurrency", "1", *extra], capsys)


def tree_nodes(book_id=HINTED):
    return list(lib.iter_nodes(lib.read_json(lib.data_dir(book_id) / "tree.json")["structure"]))


# ----------------------------------------------------------------------------- the tree

def entries(*rows):
    return [{"title": t, "page": p, "level": l} for t, p, l in rows]


def ranges(structure):
    return [(n["node_id"], n["start_index"], n["end_index"]) for n in lib.iter_nodes(structure)]


def test_nesting_and_range_math():
    toc = entries(("A", 1, 1), ("A1", 2, 2), ("A2", 4, 2), ("B", 6, 1), ("B1", 6, 2), ("C", 8, 1))
    structure = native.build_structure(native.normalize_toc(toc, 9)[0], 9)
    assert ranges(structure) == [("0000", 1, 5), ("0001", 2, 3), ("0002", 4, 5), ("0003", 6, 7), ("0004", 6, 7),
                                 ("0005", 8, 9)]
    assert [n["title"] for n in structure] == ["A", "B", "C"]          # top level
    assert [n["title"] for n in structure[0]["nodes"]] == ["A1", "A2"]  # nesting from level
    assert structure[0]["start_index"] == 1 and structure[0]["end_index"] >= structure[0]["nodes"][-1]["end_index"]


def test_one_entry_per_page_toc():
    toc = entries(*[(f"Page {i} - hint {i}", i, 1) for i in range(1, 6)])
    structure = native.build_structure(native.normalize_toc(toc, 5)[0], 5)
    assert ranges(structure) == [(f"{i - 1:04d}", i, i) for i in range(1, 6)]


def test_same_page_siblings_keep_one_page_and_levels_may_skip():
    toc = entries(("A", 3, 1), ("B", 3, 1), ("deep", 4, 3), ("C", 5, 1))
    structure = native.build_structure(native.normalize_toc(toc, 6)[0], 6)
    assert ranges(structure) == [("0000", 3, 3), ("0001", 3, 4), ("0002", 4, 4), ("0003", 5, 6)]
    assert structure[1]["nodes"][0]["title"] == "deep"


def test_unsorted_and_out_of_range_entries():
    toc = entries(("late", 5, 1), ("early", 1, 1), ("beyond", 99, 1), ("zero", 0, 1)) + [{"title": "", "page": 2}, "junk"]
    normal, dropped = native.normalize_toc(toc, 6)
    assert [e["title"] for e in normal] == ["early", "late"] and dropped == 4
    assert ranges(native.build_structure(normal, 6)) == [("0000", 1, 4), ("0001", 5, 6)]
    assert native.normalize_toc([{"title": "x", "page": 2, "level": 0}], 3)[0][0]["level"] == 1


def test_hinted_detection():
    assert native.is_hinted(fixture_json(HINTED, "toc.json")["items"][0]["toc"])
    assert not native.is_hinted(fixture_json("flat-demo", "toc.json")["items"][0]["toc"])
    assert not native.is_hinted([])
    assert not native.is_hinted(entries(("a - b", 1, 1), ("c", 2, 1)))  # exactly half is not "most"


def test_split_pages_on_level_one_headings_only():
    text = "intro line\n# Page A\nbody\n### Footnotes\n**1.** note\n# Page B\nmore\n"
    assert native.split_pages(text, r"# \S") == {1: "# Page A\nbody\n### Footnotes\n**1.** note",
                                                 2: "# Page B\nmore"}


def test_a_parent_never_ends_before_its_last_child():
    # A(1) > A1(5), then B(5): A1 ends on 5, so A must reach 5 too; page 5 is shared by A (through A1) and B
    toc = entries(("A", 1, 1), ("A1", 5, 2), ("B", 5, 1))
    assert ranges(native.build_structure(native.normalize_toc(toc, 8)[0], 8)) == [("0000", 1, 5), ("0001", 5, 5), ("0002", 5, 8)]
    deep = entries(("A", 1, 1), ("A1", 3, 2), ("A1a", 5, 3), ("B", 5, 1))
    assert ranges(native.build_structure(native.normalize_toc(deep, 8)[0], 8)) == [
        ("0000", 1, 5), ("0001", 3, 5), ("0002", 5, 5), ("0003", 5, 8)]
    shared = entries(("X", 2, 1), ("Y", 2, 2), ("Z", 2, 2), ("W", 2, 1))
    assert ranges(native.build_structure(native.normalize_toc(shared, 4)[0], 4)) == [
        ("0000", 2, 2), ("0001", 2, 2), ("0002", 2, 2), ("0003", 2, 4)]


def test_every_node_contains_its_children_for_any_toc():
    import random
    rng = random.Random(7)
    for _ in range(300):
        n = rng.randint(1, 12)
        toc = [{"title": f"t{i}", "page": rng.randint(1, n), "level": rng.randint(1, 4)} for i in range(rng.randint(1, 15))]
        structure = native.build_structure(native.normalize_toc(toc, n)[0], n)

        def check(nodes, lo, hi):
            for node in nodes:
                assert lo <= node["start_index"] <= node["end_index"] <= hi
                check(node.get("nodes") or [], node["start_index"], node["end_index"])
        check(structure, 1, n)


# ----------------------------------------------------------------------------- index-trove with summaries

def test_index_trove_writes_the_hinted_tree_and_gemini_summaries(env, capsys):
    code, out, err = index(capsys)
    assert code == 0, err
    assert set(out) == SUCCESS_KEYS
    assert out["ok"] is True and out["source"] == "trove-toc" and out["fallback"] is False
    assert out["book_id"] == out["trove_id"] == HINTED
    assert (out["nodes"], out["toc_entries"], out["hinted_entries"], out["n_pages"]) == (NODES, NODES, NODES, 9)
    assert (out["calls"], out["summaries_generated"], out["summaries_reused"], out["nodes_with_summary"]) == (NODES, NODES, 0, NODES)
    assert (out["prompt_tokens"], out["completion_tokens"], out["reasoning_tokens"]) == (10 * NODES, 5 * NODES, 2 * NODES)
    assert out["cost_usd"] == pytest.approx(0.001 * NODES) and out["model"] == "gemini/gemini-3.8-flash"
    assert out["summary_failures"] == 0 and out["expected_calls"] == NODES and out["dry_run"] is False

    nodes = tree_nodes()
    assert [(n["node_id"], n["start_index"], n["end_index"]) for n in nodes] == [
        ("0000", 1, 1), ("0001", 2, 5), ("0002", 2, 3), ("0003", 4, 5), ("0004", 6, 7), ("0005", 6, 7), ("0006", 8, 9)]
    assert nodes[1]["title"] == "Part one - The sources of law."          # the hint stays in the title, as in Trove
    assert all(("prefix_summary" in n) == bool(n.get("nodes")) for n in nodes)  # parents carry prefix_summary
    assert all(("summary" in n) != bool(n.get("nodes")) for n in nodes)         # leaves carry summary


def test_parent_summaries_are_built_from_the_child_summaries(env, capsys):
    index(capsys)
    leaf = [p for p in env.stub.prompts if "Section pages" in p]
    parent = [p for p in env.stub.prompts if "Parts:" in p]
    assert len(leaf) == 5 and len(parent) == 2
    tree = lib.read_json(lib.data_dir(HINTED) / "tree.json")["structure"]
    part_one = tree[1]
    part_one_prompt = [p for p in parent if "Part one" in p][0]
    for child in part_one["nodes"]:
        assert child["summary"] in part_one_prompt and child["title"] in part_one_prompt
    assert part_one["prefix_summary"].startswith("SUM:")
    assert "Section pages" in leaf[0] and env.stub.models[0] == "gemini/gemini-3.8-flash"
    assert env.stub.kwargs[0]["drop_params"] is True


def test_hebrew_text_reaches_the_model_and_the_library_unescaped(env, capsys):
    index(capsys)
    hebrew = [p for p in env.stub.prompts if "הלכה למשה מסיני: כְּלָל" in p]
    assert len(hebrew) == 1                                                      # niqqud intact in the prompt
    raw = (lib.data_dir(HINTED) / "tree.json").read_text(encoding="utf-8")
    assert "הלכה למשה מסיני והמסורת שבעל פה" in raw and "\\u05" not in raw      # stored as characters
    code, out, _ = run_main(["read", HINTED, "4", "--json"], capsys)
    assert json.loads(out)["pages"][0]["content"] == fixture_pages(HINTED)[3]


def test_read_back_equals_trove(env, capsys):
    index(capsys)
    code, out, _ = run_main(["read", HINTED, "all", "--json"], capsys)
    got = [p["content"] for p in json.loads(out)["pages"]]
    assert got == [t.rstrip() for t in fixture_pages(HINTED)]
    code, out, _ = run_main(["meta", HINTED], capsys)
    meta = json.loads(out)
    assert meta["trove_id"] == HINTED and meta["pagemap"] is None and meta["n_pages"] == 9
    origin = meta["origin"]["trove"]
    assert {"trove_id", "title", "trove_pages", "toc_entries", "hinted_entries", "toc_sha"} <= set(origin)
    assert (origin["trove_pages"], origin["toc_entries"], origin["hinted_entries"]) == (9, NODES, NODES)
    code, out, _ = run_main(["verify-library", "--min-books", "1", "--require-summary"], capsys)
    assert code == 0 and f"ok {HINTED}: 9 pages, {NODES} nodes, toc_source=trove-toc" in out
    code, out, _ = run_main(["catalog"], capsys)
    assert json.loads(out)[HINTED]["node_count"] == NODES
    meta_file = lib.read_json(lib.data_dir(HINTED) / "meta.json")
    assert meta_file["indexer"]["mode"] == "native-toc" and meta_file["indexer"]["llm_calls"] == NODES
    assert meta_file["page_text_source"] == "origin" and meta_file["toc_source"] == "trove-toc"


def test_trove_is_only_read(env, capsys):
    index(capsys)
    calls = [json.loads(line) for line in env.log.read_text().splitlines()]
    assert calls == [["items", "toc", HINTED, "--json", "--no-session"], ["items", "read", f"{HINTED}:all", "--json", "--no-session"]]


def test_stdout_is_one_json_line_even_when_a_library_prints(env, capsys):
    assert env.stub.noise
    code, out, err = run_main(["index-trove", HINTED, "--concurrency", "1"], capsys)
    assert code == 0 and len(out.strip().splitlines()) == 1 and json.loads(out)["ok"] is True
    assert "litellm: a line a library prints" in err


def test_book_id_and_title_overrides(env, capsys):
    code, out, _ = index(capsys, "--book-id", "shelf-copy", "--title", "A Chosen Title", "--summaries", "none")
    assert code == 0 and out["book_id"] == "shelf-copy" and out["trove_id"] == HINTED and out["title"] == "A Chosen Title"
    assert lib.catalog()["books"]["shelf-copy"]["title"] == "A Chosen Title"


# ----------------------------------------------------------------------------- summaries: hints, none, reuse

def test_summaries_hints_makes_no_model_call(env, capsys):
    code, out, _ = index(capsys, "--summaries", "hints")
    assert code == 0 and out["calls"] == 0 and out["model"] is None and out["summaries"] == "hints"
    assert env.stub.prompts == []
    nodes = tree_nodes()
    assert nodes[2]["summary"] == "The written Torah and its plain sense."
    assert nodes[1]["prefix_summary"] == "The sources of law."
    assert out["nodes_with_summary"] == NODES
    code, _, _ = run_main(["verify-library", "--min-books", "1"], capsys)  # llm_calls == 0
    assert code == 0


def test_summaries_none_is_the_model_free_tree(env, capsys):
    code, out, _ = index(capsys, "--summaries", "none")
    assert code == 0 and out["calls"] == 0 and out["nodes_with_summary"] == 0
    assert all("summary" not in n and "prefix_summary" not in n for n in tree_nodes())
    code, _, _ = run_main(["verify-library", "--min-books", "1", "--no-summary"], capsys)
    assert code == 0
    assert not (lib.book_dir(HINTED) / "summaries.json").exists()


def test_reindex_reuses_every_unchanged_summary(env, capsys):
    index(capsys)
    first = {n["node_id"]: n.get("summary") or n.get("prefix_summary") for n in tree_nodes()}
    env.stub.prompts.clear()
    code, out, _ = index(capsys)
    assert code == 0 and out["calls"] == 0 and out["summaries_reused"] == NODES and out["summaries_generated"] == 0
    assert env.stub.prompts == []
    assert {n["node_id"]: n.get("summary") or n.get("prefix_summary") for n in tree_nodes()} == first


def test_reindex_after_a_page_changes_pays_for_that_node_and_its_parents_only(env, capsys):
    index(capsys)
    path = env.data / "books" / HINTED / "read.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["items"][0]["pages"][6]["content"] += "\nA new paragraph about witnesses in a case of damages."  # Trove page 7
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    env.stub.prompts.clear()
    code, out, _ = index(capsys)
    assert code == 0 and out["calls"] == 2 and out["summaries_reused"] == NODES - 2 and out["summaries_generated"] == 2
    assert len(env.stub.prompts) == 2 and "witnesses in a case of damages" in env.stub.prompts[0]
    assert "Parts:" in env.stub.prompts[1]  # the parent "Part two" is rewritten from the new child summary


def test_dry_run_plans_without_writing_or_calling(env, capsys):
    code, out, _ = index(capsys, "--dry-run")
    assert code == 0 and out["dry_run"] is True and out["expected_calls"] == NODES and out["indexed_at"] is None
    assert out["calls"] == 0 and out["input_chars"] > 0 and env.stub.prompts == []
    assert not env.library.exists()
    index(capsys)
    code, out, _ = index(capsys, "--dry-run")
    assert code == 0 and out["expected_calls"] == 0 and out["summaries_reused"] == NODES


# ----------------------------------------------------------------------------- caps and failures

def test_call_cap_aborts_without_a_half_written_book_and_keeps_the_paid_summaries(env, capsys):
    code, out, err = index(capsys, "--max-calls", "3")
    assert code == 1 and out["ok"] is False and out["code"] == "call_cap" and FAILURE_KEYS <= set(out)
    assert out["calls"] == 3 and out["call_cap"] == 3 and "cap" in out["error"]
    assert "ERROR library index:" in err
    assert lib.data_dir(HINTED) is None and HINTED not in lib.catalog()["books"]
    cache = lib.read_json(lib.book_dir(HINTED) / "summaries.json")["entries"]
    assert len(cache) == 3
    code, out, _ = index(capsys)
    assert code == 0 and out["calls"] == NODES - 3 and out["summaries_reused"] == 3


def test_a_failed_reindex_leaves_the_old_book_readable(env, capsys):
    index(capsys, "--summaries", "none")
    before = (lib.data_dir(HINTED) / "tree.json").read_bytes()
    code, out, _ = index(capsys, "--max-calls", "1")
    assert code == 1 and out["code"] == "call_cap"
    assert (lib.data_dir(HINTED) / "tree.json").read_bytes() == before
    code, _, _ = run_main(["read", HINTED, "1", "--json"], capsys)
    assert code == 0


def test_a_model_that_never_answers_stops_early_and_never_prints_the_key(env, capsys):
    env.stub.fail_when = lambda prompt: True
    env.stub.fail_text = "API key not valid: AIzaSyDUMMYDUMMYDUMMYDUMMYDUMMY1234"
    code, out, err = index(capsys)
    assert code == 1 and out["code"] == "model_failed" and out["failures"] >= summarize.EARLY_ABORT_FAILURES
    assert "AIza" not in json.dumps(out) and "AIza" not in err
    assert lib.data_dir(HINTED) is None
    assert len(env.stub.prompts) < NODES * summarize.ATTEMPTS + 1  # it stopped before trying every node


def test_one_failing_node_is_reported_and_the_retry_pays_only_for_it(env, capsys):
    env.stub.fail_when = lambda prompt: "הלכה למשה מסיני: כְּלָל" in prompt
    code, out, _ = index(capsys)
    assert code == 0 and out["summary_failures"] == 1 and out["nodes_with_summary"] == NODES - 1
    assert out["calls"] == NODES - 1 + summarize.ATTEMPTS and out["failures"] == summarize.ATTEMPTS
    env.stub.fail_when = None
    env.stub.prompts.clear()
    code, out, _ = index(capsys)
    assert code == 0 and out["summary_failures"] == 0 and out["nodes_with_summary"] == NODES
    assert out["summaries_generated"] == 2  # the failed leaf, and its parent now that it has all its children


def test_missing_key_fails_before_any_call_and_offers_the_free_modes(env, capsys, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    code, out, err = index(capsys)
    assert code == 1 and out["code"] == "missing_key" and "--summaries hints" in out["error"]
    assert env.stub.prompts == []
    code, out, _ = index(capsys, "--summaries", "hints")
    assert code == 0


def test_the_plugin_google_key_is_enough(env, capsys, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-real")
    code, out, _ = index(capsys)
    assert code == 0 and os.environ["GEMINI_API_KEY"] == "test-key-not-real"
    monkeypatch.delenv("GEMINI_API_KEY")


def test_another_provider_needs_no_gemini_key(env, capsys, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    code, out, _ = index(capsys, "--model", "stub/other")
    assert code == 0 and out["model"] == "stub/other" and env.stub.models[0] == "stub/other"


def test_litellm_missing_is_a_plain_error(env, capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "litellm", None)
    code, out, err = index(capsys)
    assert code == 1 and out["code"] == "core_helper_missing" and "--summaries hints" in out["error"]


def test_trove_errors_are_plain(env, capsys, monkeypatch):
    code, out, err = index(capsys, book="no-such-book")
    assert code == 1 and out["code"] == "trove_failed" and "no such item" in out["error"]
    monkeypatch.setenv("FAKE_TROVE_TRUNCATED", "1")
    code, out, _ = index(capsys)
    assert code == 1 and out["code"] == "trove_truncated"
    monkeypatch.delenv("FAKE_TROVE_TRUNCATED")
    empty = env.tmp / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    code, out, _ = index(capsys)
    assert code == 1 and out["code"] == "trove_failed" and "not found" in out["error"]


def test_an_unexpected_error_is_still_one_json_object(env, capsys, monkeypatch):
    def boom(*a, **kw):
        raise KeyError("surprise")
    monkeypatch.setattr(native, "build_structure", boom)
    code, out, err = index(capsys)
    assert code == 1 and out["code"] == "internal" and "KeyError" in out["error"]


# ----------------------------------------------------------------------------- no hinted ToC: fallback

PLAIN_ERROR = "this book has no hinted table of contents and the structure helper is not installed"


def test_no_hinted_toc_without_the_structure_helper(env, capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "pageindex", None)
    monkeypatch.setitem(sys.modules, "pageindex.flash", None)
    monkeypatch.setitem(sys.modules, "pageindex.flash.api", None)
    code, out, err = index(capsys, book="flat-demo")
    assert code == 1 and out["code"] == "structure_helper_missing" and out["error"] == PLAIN_ERROR
    assert f"ERROR library index: {PLAIN_ERROR}" in err
    assert env.stub.prompts == [] and "flat-demo" not in lib.catalog()["books"]


def test_no_fallback_refuses_a_book_without_hints(env, capsys):
    code, out, err = index(capsys, "--no-fallback", book="flat-demo")
    assert code == 1 and out["code"] == "no_hinted_toc" and "no hinted table of contents" in err


def install_structure_stubs(monkeypatch, tmp_path, flash):
    """PageIndex and WeasyPrint are not installed in the tests: stub both, and the PDF render."""
    pageindex, sub, api = types.ModuleType("pageindex"), types.ModuleType("pageindex.flash"), types.ModuleType("pageindex.flash.api")
    api.page_index_flash = flash
    for name, module in (("pageindex", pageindex), ("pageindex.flash", sub), ("pageindex.flash.api", api),
                         ("weasyprint", types.ModuleType("weasyprint"))):
        monkeypatch.setitem(sys.modules, name, module)
    from pilib import render_trove
    seen = {}

    def render(pages, title, out):
        seen["pages"] = dict(pages)
        out.write_bytes(b"%PDF-stub")
        return [1, 1, 2, 3, 3, 4]  # six PDF pages for four Trove pages

    def verify(pdf, pages, mapping):
        return {"pdf_pages": 6, "trove_pages": 4, "min_word_overlap": 0.99, "worst_trove_page": 2,
                "mean_word_overlap": 0.99, "min_bigram_overlap": 0.9, "hebrew_pages": 0, "hebrew_min": None, "pages": {}}
    monkeypatch.setattr(render_trove, "render", render)
    monkeypatch.setattr(render_trove, "verify", verify)
    return seen


def test_no_hinted_toc_uses_page_index_structure_detection(env, capsys, monkeypatch):
    calls = []

    def flash(pdf, **kwargs):
        calls.append(kwargs)
        import litellm
        for _ in range(2):  # PageIndex writes summaries through the litellm module, which the meter counts
            litellm.completion(model=kwargs["summary_model"], messages=[{"role": "user", "content": "summarise"}])
        return {"doc_name": "book", "toc_source": "detected", "structure": [
            {"node_id": "0000", "title": "A", "start_index": 1, "end_index": 3, "summary": "s", "text": "drop me",
             "nodes": [{"node_id": "0001", "title": "A.1", "start_index": 2, "end_index": 3, "summary": "t"}]},
            {"node_id": "0002", "title": "B", "start_index": 4, "end_index": 6, "summary": "u"}]}
    seen = install_structure_stubs(monkeypatch, env.tmp, flash)
    code, out, err = index(capsys, book="flat-demo")
    assert code == 0, err
    assert out["source"] == "flash-structure" and out["fallback"] is True and set(out) == SUCCESS_KEYS
    assert out["calls"] == 2 and out["prompt_tokens"] == 20 and out["nodes"] == 3 and out["toc_entries"] == 4
    assert "PageIndex detected its structure" in out["warnings"][0]
    assert calls[0]["summary"] is True and calls[0]["optimize"] == "full" and calls[0]["use_embedded_toc"] is False
    assert calls[0]["summary_model"] == "gemini/gemini-3.8-flash"
    # PDF page numbers are mapped back to Trove pages: A is PDF 1-3 -> Trove 1-2, B is PDF 4-6 -> Trove 3-4
    nodes = tree_nodes("flat-demo")
    assert [(n["title"], n["start_index"], n["end_index"]) for n in nodes] == [("A", 1, 2), ("A.1", 1, 2), ("B", 3, 4)]
    assert all("text" not in n for n in nodes)
    code, out, _ = run_main(["read", "flat-demo", "all", "--json"], capsys)
    assert [p["content"] for p in json.loads(out)["pages"]] == [t.rstrip() for t in fixture_pages("flat-demo")]  # Trove text, not the PDF's
    meta = lib.read_json(lib.data_dir("flat-demo") / "meta.json")
    assert meta["toc_source"] == "flash-detected" and meta["indexer"]["mode"] == "flash-structure"
    assert meta["indexer"]["pageindex_commit"].startswith("af92d96") and meta["indexer"]["llm_calls"] == 2
    assert meta["origin"]["trove"]["trove_id"] == "flat-demo" and meta["origin"]["trove"]["hinted_entries"] == 0
    assert set(seen["pages"]) == {1, 2, 3, 4}


def test_structure_fallback_without_summaries_makes_no_model_call(env, capsys, monkeypatch):
    calls = []

    def flash(pdf, **kwargs):
        calls.append(kwargs)
        return {"toc_source": "pages", "structure": [{"node_id": "0000", "title": "Page 1", "start_index": 1, "end_index": 6}]}
    install_structure_stubs(monkeypatch, env.tmp, flash)
    code, out, _ = index(capsys, "--summaries", "none", book="flat-demo")
    assert code == 0 and out["calls"] == 0 and calls[0]["summary"] is False and calls[0]["optimize"] is False
    assert env.stub.prompts == []
    assert tree_nodes("flat-demo")[0]["end_index"] == 4
    code, out, _ = index(capsys, "--summaries", "hints", book="flat-demo")
    assert code == 0 and out["summaries"] == "none" and any("hints" in w for w in out["warnings"])


def test_structure_fallback_respects_the_call_cap(env, capsys, monkeypatch):
    def flash(pdf, **kwargs):
        import litellm
        for _ in range(5):
            litellm.completion(model="gemini/x", messages=[{"role": "user", "content": "s"}])
        return {"structure": []}
    install_structure_stubs(monkeypatch, env.tmp, flash)
    code, out, _ = index(capsys, "--max-calls", "2", book="flat-demo")
    assert code == 1 and out["code"] == "call_cap" and out["calls"] == 2
    assert "flat-demo" not in lib.catalog()["books"]


# ----------------------------------------------------------------------------- index-md

def md_inputs(tmp_path, book=HINTED):
    pages = fixture_pages(book)
    pages_md = tmp_path / "pages.md"
    pages_md.write_text("\n\n".join(pages) + "\n", encoding="utf-8")
    toc = tmp_path / "toc.json"
    toc.write_text(json.dumps(fixture_json(book, "toc.json")["items"][0]["toc"], ensure_ascii=False), encoding="utf-8")
    return pages_md, toc


def test_index_md_is_the_same_tree_offline(env, capsys):
    pages_md, toc = md_inputs(env.tmp)
    code, out, err = run_json(["index-md", "--pages", str(pages_md), "--toc", str(toc), "--book-id", "md-book",
                               "--title", "An Offline Book", "--summaries", "hints"], capsys)
    assert code == 0, err
    assert set(out) == SUCCESS_KEYS and out["source"] == "markdown-toc" and out["trove_id"] is None
    assert out["n_pages"] == 9 and out["nodes"] == NODES and out["calls"] == 0
    nodes = tree_nodes("md-book")
    assert [(n["start_index"], n["end_index"]) for n in nodes] == [(1, 1), (2, 5), (2, 3), (4, 5), (6, 7), (6, 7), (8, 9)]
    pages = lib.read_json(lib.data_dir("md-book") / "pages.json")
    assert pages[3].startswith("# עמוד מקורי 3") and "### Footnotes" in pages[4]
    assert lib.read_json(lib.data_dir("md-book") / "meta.json")["origin"]["md"]["pages"] == 9
    assert not [c for c in env.log.parent.glob("trove-calls.log")]  # no Trove call at all


def test_index_md_one_entry_per_page_and_summaries_none(env, capsys):
    pages_md, _ = md_inputs(env.tmp, "flat-demo")
    toc = env.tmp / "toc.json"
    toc.write_text(json.dumps({"toc": fixture_json("flat-demo", "toc.json")["items"][0]["toc"]}), encoding="utf-8")
    code, out, _ = run_json(["index-md", "--pages", str(pages_md), "--toc", str(toc), "--book-id", "flat",
                             "--title", "Flat", "--summaries", "none"], capsys)
    assert code == 0 and out["nodes"] == 4
    assert [(n["start_index"], n["end_index"]) for n in tree_nodes("flat")] == [(1, 1), (2, 2), (3, 3), (4, 4)]


def test_index_md_bad_inputs(env, capsys):
    pages_md, toc = md_inputs(env.tmp)
    code, out, _ = run_json(["index-md", "--pages", str(pages_md), "--toc", str(env.tmp / "missing.json"),
                             "--book-id", "x", "--title", "X", "--summaries", "none"], capsys)
    assert code == 1 and out["code"] == "bad_input"
    code, out, _ = run_json(["index-md", "--pages", str(pages_md), "--toc", str(toc), "--book-id", "x", "--title", "X",
                             "--page-marker", "NEVER", "--summaries", "none"], capsys)
    assert code == 1 and out["code"] == "empty_book"
    empty = env.tmp / "empty.json"
    empty.write_text("[]")
    code, out, _ = run_json(["index-md", "--pages", str(pages_md), "--toc", str(empty), "--book-id", "x", "--title", "X",
                             "--summaries", "none"], capsys)
    assert code == 1 and out["code"] == "no_toc"


def test_index_md_runs_as_a_plain_process_without_litellm(env, tmp_path):
    pages_md, toc = md_inputs(env.tmp)
    child_env = {**os.environ, "PYTHONPATH": str(PKG), "AW_LIBRARY": str(env.tmp / "proc-library")}
    proc = subprocess.run([sys.executable, "-m", "pilib", "index-md", "--pages", str(pages_md), "--toc", str(toc),
                           "--book-id", "proc", "--title", "Proc", "--summaries", "none"],
                          capture_output=True, text=True, env=child_env)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["nodes"] == NODES
    proc = subprocess.run([sys.executable, "-m", "pilib", "verify-library", "--min-books", "1", "--no-summary"],
                          capture_output=True, text=True, env=child_env)
    assert proc.returncode == 0, proc.stderr


# ----------------------------------------------------------------------------- the contract document

def test_contract_lists_every_field_and_code():
    for key in SUCCESS_KEYS | FAILURE_KEYS:
        assert f"`{key}`" in CONTRACT, f"contract.md does not describe {key}"
    for code in ("trove_failed", "trove_truncated", "no_hinted_toc", "structure_helper_missing", "core_helper_missing",
                 "missing_key", "call_cap", "model_failed", "bad_input", "empty_book", "no_toc", "empty_tree", "render_failed", "structure_failed", "busy", "internal"):
        assert f"`{code}`" in CONTRACT, f"contract.md does not describe the code {code}"


# ----------------------------------------------------------------------------- review fixes: publish, catalog, ids, intro

def snapshot(book_id):
    """Every file under the book folder, by relative path."""
    d = lib.book_dir(book_id)
    return {str(f.relative_to(d)): f.read_bytes() for f in sorted(d.rglob("*")) if f.is_file()}


def prune(book_id):
    with lib.book_lock(book_id):
        lib.prune_versions(book_id)


def new_version(book_id):
    with lib.book_lock(book_id):
        return lib.new_version(book_id)


def version_names(book_id):
    return sorted(d.name for d in (lib.book_dir(book_id) / "v").iterdir())


def test_a_book_is_a_current_pointer_and_a_complete_version(env, capsys):
    index(capsys, "--summaries", "none")
    container = lib.book_dir(HINTED)
    name = (container / "CURRENT").read_text().strip()
    assert (container / "v" / name).is_dir() and version_names(HINTED) == [name]
    assert sorted(f.name for f in (container / "v" / name).iterdir()) == ["meta.json", "pages.json", "tree.json"]
    assert not [f for f in container.iterdir() if f.name.startswith(".CURRENT")]
    assert lib.data_dir(HINTED) == container / "v" / name


def test_a_failed_write_leaves_the_previous_book_exactly_as_it_was(env, capsys, monkeypatch):
    index(capsys, "--summaries", "none")
    before = snapshot(HINTED)
    path = env.data / "books" / HINTED / "read.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["items"][0]["pages"][0]["content"] = "a changed first page"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    real = lib.write_json

    def failing(target, data):
        if Path(target).name == "tree.json":
            raise OSError("disk full")
        return real(target, data)
    monkeypatch.setattr(lib, "write_json", failing)
    code, out, err = index(capsys, "--summaries", "none")
    assert code == 1 and out["ok"] is False
    monkeypatch.setattr(lib, "write_json", real)
    assert snapshot(HINTED) == before                       # no file of the new generation is left, none changed
    code, out, _ = run_main(["read", HINTED, "1", "--json"], capsys)
    assert "a changed first page" not in out


def test_a_crash_before_the_pointer_moves_changes_nothing_a_reader_sees(env, capsys, monkeypatch):
    index(capsys, "--summaries", "none")
    old_tree = (lib.data_dir(HINTED) / "tree.json").read_bytes()
    old_name = lib.current_name(HINTED)
    # a run that finished writing its version and died before publishing: simulated by calling the steps by hand
    version = new_version(HINTED)
    lib.write_json(version / "pages.json", ["x"])
    lib.write_json(version / "tree.json", {"book_id": HINTED, "title": "unpublished", "n_pages": 1, "structure": []})
    lib.write_json(version / "meta.json", {"book_id": HINTED, "title": "unpublished"})
    assert lib.current_name(HINTED) == old_name and (lib.data_dir(HINTED) / "tree.json").read_bytes() == old_tree
    assert lib.catalog()["books"][HINTED]["title"] != "unpublished"
    code, out, _ = run_main(["read", HINTED, "all", "--json"], capsys)
    assert len(json.loads(out)["pages"]) == 9
    # the pointer write itself failing is also harmless, and leaves no temporary file
    real = lib.os.replace

    def failing(src, dst):
        if Path(dst).name == "CURRENT":
            raise OSError("no space")
        return real(src, dst)
    monkeypatch.setattr(lib.os, "replace", failing)
    code, out, _ = index(capsys, "--summaries", "none")
    monkeypatch.setattr(lib.os, "replace", real)
    assert code == 1 and lib.current_name(HINTED) == old_name
    assert not [f for f in lib.book_dir(HINTED).iterdir() if f.name.startswith(".CURRENT")]
    assert (lib.data_dir(HINTED) / "tree.json").read_bytes() == old_tree
    assert version.name in version_names(HINTED)            # the unreferenced version stays until it is old


def test_pruning_waits_an_hour_from_completion_and_never_touches_current_or_the_previous(env, capsys, monkeypatch):
    import time
    now = [time.time()]
    monkeypatch.setattr(lib, "clock", lambda: now[0])
    seen = []
    for _ in range(4):
        index(capsys, "--summaries", "none")
        seen.append(lib.current_name(HINTED))
    assert version_names(HINTED) == sorted(seen)            # nothing is an hour old: nothing is removed
    now[0] += lib.PRUNE_GRACE_SECONDS - 60
    prune(HINTED)
    assert version_names(HINTED) == sorted(seen)            # still inside the hour (measured from meta.indexed_at)
    now[0] += 3600
    prune(HINTED)
    assert version_names(HINTED) == sorted(seen[-2:])       # the current one and the newest complete one before it
    now[0] += 10 * 365 * 86400
    prune(HINTED)
    assert version_names(HINTED) == sorted(seen[-2:])       # however old, those two stay


def test_the_grace_is_measured_from_the_completion_time_in_meta_not_from_the_folder(env, capsys, monkeypatch):
    import time
    index(capsys, "--summaries", "none")
    index(capsys, "--summaries", "none")
    index(capsys, "--summaries", "none")
    oldest, middle, current = version_names(HINTED)
    stale = lib.book_dir(HINTED) / "v" / oldest
    os.utime(stale, (0, 0))                                  # an ancient folder time must not make it prunable
    os.utime(stale / "meta.json", (0, 0))
    prune(HINTED)
    assert oldest in version_names(HINTED)
    meta = lib.read_json(stale / "meta.json")
    meta["indexed_at"] = "2001-01-01T00:00:00+00:00"        # but a completion time long ago does
    lib.write_json(stale / "meta.json", meta)
    prune(HINTED)
    assert oldest not in version_names(HINTED) and {middle, current} <= set(version_names(HINTED))


def test_an_unfinished_version_is_pruned_only_an_hour_after_it_started(env, capsys, monkeypatch):
    import time
    index(capsys, "--summaries", "none")
    running = new_version(HINTED)                        # another run, still writing: no meta.json yet
    (running / "pages.json").write_text("[]")
    index(capsys, "--summaries", "none")
    assert running.name in version_names(HINTED)
    monkeypatch.setattr(lib, "clock", lambda: time.time() + lib.PRUNE_GRACE_SECONDS + 60)
    prune(HINTED)
    assert running.name not in version_names(HINTED)


def test_a_failure_after_the_pointer_moved_never_deletes_the_published_version(env, capsys, monkeypatch):
    index(capsys, "--summaries", "none")
    old = lib.current_name(HINTED)

    def broken(book_id):
        raise RuntimeError("cleanup failed")
    monkeypatch.setattr(lib, "prune_versions", broken)
    code, out, err = index(capsys, "--summaries", "none")   # tidy-up errors are reported, not fatal
    assert code == 0 and out["ok"] is True
    new = lib.current_name(HINTED)
    assert new != old and (lib.data_dir(HINTED) / "meta.json").is_file() and lib.data_dir(HINTED).name == new
    assert "cleanup failed" in err

    def interrupted(book_id):
        raise KeyboardInterrupt
    monkeypatch.setattr(lib, "prune_versions", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_main(["index-trove", HINTED, "--concurrency", "1", "--summaries", "none"], capsys)
    newest = lib.current_name(HINTED)
    assert newest not in (old, new)                          # the pointer had moved before the interrupt
    assert len(json.loads(run_main(["read", HINTED, "all", "--json"], capsys)[1])["pages"]) == 9
    assert lib.data_dir(HINTED).name == newest and (lib.data_dir(HINTED) / "tree.json").is_file()


def test_a_failure_before_the_pointer_moves_removes_only_the_unpublished_version(env, capsys, monkeypatch):
    index(capsys, "--summaries", "none")
    before = version_names(HINTED)
    monkeypatch.setattr(lib, "publish_version", lambda book_id, version: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        run_main(["index-trove", HINTED, "--concurrency", "1", "--summaries", "none"], capsys)
    assert version_names(HINTED) == before and lib.data_dir(HINTED) is not None


def test_a_legacy_flat_book_is_read_and_then_replaced_by_a_version(env, capsys):
    flat = lib.book_dir(HINTED)
    lib.write_json(flat / "pages.json", ["old one", "old two"])
    lib.write_json(flat / "tree.json", {"book_id": HINTED, "title": "Old", "author": "", "n_pages": 2, "toc_source": "bookmarks",
                                        "structure": [{"node_id": "0000", "title": "All", "start_index": 1, "end_index": 2}]})
    lib.write_json(flat / "meta.json", {"book_id": HINTED, "title": "Old", "origin": {}, "indexer": {"llm_calls": 0}, "n_pages": 2})
    lib.write_json(flat / "pagemap.json", {"trove_id": HINTED, "pdf_to_trove": [1, 1, 2]})
    code, out, _ = run_main(["read", HINTED, "2", "--json"], capsys)
    assert json.loads(out)["pages"][0]["content"] == "old two"
    assert json.loads(run_main(["meta", HINTED], capsys)[1])["pagemap"] == [1, 1, 2]
    assert lib.catalog()["books"][HINTED]["title"] == "Old"
    assert run_main(["list"], capsys)[1] == f"{HINTED}\t2 pp\tbookmarks\tOld\n"
    index(capsys, "--summaries", "none")                     # re-index: versioned, flat files and the page map gone
    assert (flat / "CURRENT").is_file() and not (flat / "tree.json").exists() and not (flat / "pagemap.json").exists()
    assert json.loads(run_main(["meta", HINTED], capsys)[1])["pagemap"] is None
    assert len(json.loads(run_main(["read", HINTED, "all", "--json"], capsys)[1])["pages"]) == 9
    assert lib.catalog()["books"][HINTED]["title"] == "A Demo Book of Law"


def test_the_summary_cache_survives_a_new_version(env, capsys):
    index(capsys)
    assert len(lib.read_json(lib.book_dir(HINTED) / "summaries.json")["entries"]) == NODES
    code, out, _ = index(capsys)
    assert out["calls"] == 0


def test_the_catalog_is_always_scanned(env, capsys):
    index(capsys, "--summaries", "none")
    index(capsys, "--summaries", "none", "--book-id", "second")
    assert set(lib.catalog()["books"]) == {HINTED, "second"}
    assert not (env.library / "catalog.json").exists()       # nothing to go stale
    (env.library / "catalog.json").write_text('{"books": {"ghost": {}}}')   # a leftover file is never read
    assert set(lib.catalog()["books"]) == {HINTED, "second"}
    code, out, _ = run_main(["list"], capsys)
    assert out.count("\n") == 2
    code, out, _ = index(capsys, "--summaries", "none", "--book-id", "second", "--title", "Renamed")
    assert lib.catalog()["books"]["second"]["title"] == "Renamed"   # the latest meta, at once


def spawn_index(env, pages_md, toc, book_id, title):
    child_env = {**os.environ, "PYTHONPATH": str(PKG), "AW_LIBRARY": str(env.library)}
    return subprocess.Popen([sys.executable, "-m", "pilib", "index-md", "--pages", str(pages_md), "--toc", str(toc),
                             "--book-id", book_id, "--title", title, "--summaries", "none"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=child_env)


def test_concurrent_indexers_and_readers_always_see_whole_books(env):
    pages_md, toc = md_inputs(env.tmp)
    procs = {f"par-{i}": spawn_index(env, pages_md, toc, f"par-{i}", f"P{i}") for i in range(6)}
    finished = set()
    while len(finished) < len(procs):
        for book_id, proc in procs.items():
            if proc.poll() is not None:
                finished.add(book_id)
        snapshot_ = lib.catalog()["books"]                   # a reader, interleaved with the writers
        assert finished <= set(snapshot_), "a finished indexer's book is missing from the catalog"
        for book_id, entry in snapshot_.items():
            assert entry["title"] == "P" + book_id.split("-")[1] and entry["n_pages"] == 9 and entry["node_count"] == NODES
            assert len(lib.load_pages(book_id)) == 9 and len(lib.load_tree(book_id)["structure"]) == 4
    assert all(proc.wait() == 0 for proc in procs.values())
    assert sorted(lib.catalog()["books"]) == sorted(procs)


def test_concurrent_indexers_of_the_same_book_leave_one_whole_book(env):
    pages_md, toc = md_inputs(env.tmp)
    for _ in range(3):
        procs = [spawn_index(env, pages_md, toc, "same", f"Title {i}") for i in range(5)]
        while any(p.poll() is None for p in procs):
            folder = lib.data_dir("same")                    # readers meanwhile: one version, whole
            if folder is not None:
                tree, meta = lib.read_json(folder / "tree.json"), lib.read_json(folder / "meta.json")
                assert tree["title"] == meta["title"] and len(lib.read_json(folder / "pages.json")) == 9
        results = [(p.wait(), p.communicate()[0].decode()) for p in procs]
        assert any(code == 0 for code, _ in results)
        for code, out in results:                            # a loser is told so, as JSON, and changes nothing
            assert code == 0 or json.loads(out)["code"] == "busy"
    final = lib.data_dir("same")
    assert lib.read_json(final / "tree.json")["title"] == lib.read_json(final / "meta.json")["title"]
    assert lib.catalog()["books"]["same"]["title"] == lib.read_json(final / "meta.json")["title"]
    assert (lib.book_dir("same") / "CURRENT").read_text().strip() in version_names("same")
    assert not (lib.book_dir("same") / ".index.lock").exists()


@pytest.mark.parametrize("bad", ["..", "a/b", ".hidden", "a..b", "", "x y", "../x", "a\\b"])
def test_book_ids_are_validated(env, bad):
    with pytest.raises(ValueError):
        lib.book_dir(bad)


def test_a_book_directory_cannot_leave_the_library(env, capsys):
    outside = env.tmp / "outside"
    outside.mkdir()
    (env.library / "books").mkdir(parents=True)
    (env.library / "books" / "evil").symlink_to(outside)
    with pytest.raises(ValueError):
        lib.book_dir("evil")
    code, out, err = index(capsys, "--summaries", "none", "--book-id", "evil")
    assert code == 1 and out["code"] == "bad_input" and list(outside.iterdir()) == []
    code, _, err = run_main(["read", "evil", "1"], capsys)
    assert code == 1 and "evil" in err
    (env.library / "books" / "evil").unlink()
    (env.library / "books").rmdir()
    (env.library / "books").symlink_to(outside)                           # the whole books folder points out
    with pytest.raises(ValueError):
        lib.book_dir("fine")
    code, out, _ = index(capsys, "--summaries", "none")
    assert code == 1 and out["code"] == "bad_input" and list(outside.iterdir()) == []


def test_versions_and_the_pointer_obey_the_same_containment_rules(env, capsys):
    index(capsys, "--summaries", "none")
    container = lib.book_dir(HINTED)
    outside = env.tmp / "elsewhere"
    outside.mkdir()
    for name in ("tree.json", "pages.json", "meta.json"):
        (outside / name).write_text("[]" if name == "pages.json" else "{}")
    current = (container / "CURRENT").read_text()
    (container / "CURRENT").write_text("../../../elsewhere\n")                  # a pointer that names a path
    with pytest.raises(ValueError):
        lib.data_dir(HINTED)
    assert HINTED not in lib.catalog()["books"]
    (container / "CURRENT").unlink()
    (container / "CURRENT").symlink_to(outside / "tree.json")                   # a symlinked pointer
    with pytest.raises(ValueError):
        lib.data_dir(HINTED)
    code, out, _ = index(capsys, "--summaries", "none")
    assert code == 1 and out["code"] == "bad_input" and (outside / "tree.json").read_text() == "{}"
    (container / "CURRENT").unlink()
    (container / "CURRENT").write_text(current)
    name = current.strip()
    real_version = container / "v" / name
    moved = container / "v-real"
    (container / "v").rename(moved)
    (container / "v").symlink_to(moved)                                         # a symlinked versions folder
    with pytest.raises(ValueError):
        lib.data_dir(HINTED)
    code, out, _ = index(capsys, "--summaries", "none")
    assert code == 1 and out["code"] == "bad_input"
    (container / "v").unlink()
    moved.rename(container / "v")
    link = container / "v" / "99999999999999999999-deadbeef"
    link.symlink_to(outside)                                                     # a version folder that is a link
    (container / "CURRENT").write_text(link.name + "\n")
    with pytest.raises(ValueError):
        lib.data_dir(HINTED)


def test_text_before_a_parents_first_child_reaches_its_summary(env, capsys):
    pages = [f"# Page {i}\n\nUnique text of page {i}." for i in range(1, 6)]
    pages_md = env.tmp / "p.md"
    pages_md.write_text("\n\n".join(pages) + "\n", encoding="utf-8")
    toc = env.tmp / "t.json"
    toc.write_text(json.dumps(entries(("Parent", 1, 1), ("Child", 3, 2), ("Other", 5, 1))), encoding="utf-8")
    argv = ["index-md", "--pages", str(pages_md), "--toc", str(toc), "--book-id", "intro", "--title", "I", "--concurrency", "1"]
    code, out, _ = run_json(argv, capsys)
    assert code == 0 and out["calls"] == 3
    parent = [p for p in env.stub.prompts if "Parts:" in p][0]
    assert "Unique text of page 1." in parent and "Unique text of page 2." in parent and "Unique text of page 3." not in parent
    assert parent.index("Unique text of page 2.") < parent.index("Child")                     # intro first, then the subsections
    pages[1] = "# Page 2\n\nA rewritten opening."
    pages_md.write_text("\n\n".join(pages) + "\n", encoding="utf-8")
    env.stub.prompts.clear()
    code, out, _ = run_json(argv, capsys)
    assert code == 0 and out["calls"] == 1 and out["summaries_reused"] == 2                  # only the parent is rewritten


def test_a_render_failure_is_a_json_failure_not_a_bare_exit(env, capsys, monkeypatch):
    def flash(pdf, **kwargs):
        return {"structure": []}
    install_structure_stubs(monkeypatch, env.tmp, flash)
    from pilib import render_trove

    def broken(pages, title, out):
        raise SystemExit("anchors lost for Trove pages [2]")
    monkeypatch.setattr(render_trove, "render", broken)
    code, out, err = index(capsys, "--summaries", "none", book="flat-demo")
    assert code == 1 and out["code"] == "render_failed" and "anchors lost" in out["error"]
    assert "ERROR library index:" in err
    monkeypatch.setattr(render_trove, "render", lambda pages, title, path: [1, 2, 3, 4])

    def bad_verify(pdf, pages, mapping):
        raise SystemExit("pagemap has 4 entries but the PDF has 5 pages")
    monkeypatch.setattr(render_trove, "verify", bad_verify)
    code, out, _ = index(capsys, "--summaries", "none", book="flat-demo")
    assert code == 1 and out["code"] == "render_failed"


def test_any_stray_exit_is_still_one_json_object(env, capsys, monkeypatch):
    monkeypatch.setattr(native, "build_structure", lambda *a, **k: (_ for _ in ()).throw(SystemExit("stray")))
    code, out, err = index(capsys)
    assert code == 1 and out["ok"] is False and out["code"] == "internal" and "stray" in out["error"]


# ----------------------------------------------------------------------------- one indexer per book

BUSY = "this book is being indexed by another process \u2014 try again when it finishes"


def hold_lock_in_another_process(env, book_id):
    code = ("import sys; sys.path.insert(0, %r)\nfrom pilib import library as lib\n"
            "with lib.book_lock(%r):\n    print('locked', flush=True)\n    sys.stdin.read()\n" % (str(PKG), book_id))
    proc = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                            env={**os.environ, "AW_LIBRARY": str(env.library)})
    assert proc.stdout.readline().strip() == "locked"
    return proc


def release(proc):
    proc.stdin.close()
    proc.wait(timeout=20)


def test_a_second_indexer_of_the_same_book_is_told_busy_at_once(env, capsys):
    holder = hold_lock_in_another_process(env, HINTED)
    try:
        code, out, err = index(capsys, "--summaries", "none")
        assert code == 1 and out["ok"] is False and out["code"] == "busy" and out["error"] == BUSY
        assert f"ERROR library index: {BUSY}" in err
        assert lib.data_dir(HINTED) is None                  # nothing was written
        code, out, _ = index(capsys, "--summaries", "none", "--dry-run")
        assert code == 0                                      # a dry run writes nothing, so it needs no lock
        code, out, _ = index(capsys, "--summaries", "none", "--book-id", "another-book")
        assert code == 0 and out["book_id"] == "another-book"  # other books index in parallel
    finally:
        release(holder)
    code, out, _ = index(capsys, "--summaries", "none")       # the holder has gone: its lock is free
    assert code == 0 and not (lib.book_dir(HINTED) / ".index.lock").exists()


def test_the_lock_names_its_holder_and_is_released_on_any_exit(env):
    with lib.book_lock(HINTED):
        token = json.loads((lib.book_dir(HINTED) / ".index.lock").read_text())
        assert token["pid"] == os.getpid() and token["nonce"] and token["started"] > 0
        with pytest.raises(lib.BookBusy):
            with lib.book_lock(HINTED):                      # not even the same process takes it twice
                pass
    assert not (lib.book_dir(HINTED) / ".index.lock").exists()
    with pytest.raises(KeyboardInterrupt):
        with lib.book_lock(HINTED):
            raise KeyboardInterrupt
    assert not (lib.book_dir(HINTED) / ".index.lock").exists()


def test_a_lock_left_by_a_dead_process_is_taken_over(env, capsys):
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    lock = lib.book_dir(HINTED) / ".index.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({"pid": dead.pid, "nonce": "old", "started": __import__("time").time()}))
    code, out, _ = index(capsys, "--summaries", "none")
    assert code == 0 and not lock.exists()
    # a holder that is alive but far too old is also taken over (its pid may have been reused)
    lock.write_text(json.dumps({"pid": os.getpid(), "nonce": "old", "started": __import__("time").time() - 10 * 3600}))
    code, out, _ = index(capsys, "--summaries", "none")
    assert code == 0 and not lock.exists()
    # an unreadable lock is a creator that is still writing; only an old one is taken over
    lock.write_text("")
    code, out, _ = index(capsys, "--summaries", "none")
    assert code == 1 and out["code"] == "busy"
    os.utime(lock, (0, 0))
    code, out, _ = index(capsys, "--summaries", "none")
    assert code == 0 and not lock.exists()


def test_a_live_holder_is_never_taken_over(env, capsys):
    lock = lib.book_dir(HINTED) / ".index.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({"pid": os.getppid(), "nonce": "other", "started": __import__("time").time()}))
    code, out, _ = index(capsys, "--summaries", "none")
    assert code == 1 and out["code"] == "busy" and json.loads(lock.read_text())["nonce"] == "other"


def test_a_lock_is_released_only_with_its_own_nonce(env):
    lock = lib.book_dir(HINTED) / ".index.lock"
    with lib.book_lock(HINTED):
        lock.write_text(json.dumps({"pid": os.getppid(), "nonce": "someone-else", "started": __import__("time").time()}))
    assert json.loads(lock.read_text())["nonce"] == "someone-else"   # ours had been taken over: leave theirs alone


def test_publish_and_prune_need_the_lock_and_read_the_pointer_under_it(env, capsys, monkeypatch):
    import time
    index(capsys, "--summaries", "none")
    for call in (lambda: lib.new_version(HINTED), lambda: lib.prune_versions(HINTED),
                 lambda: lib.publish_version(HINTED, lib.book_dir(HINTED) / "v" / "x")):
        with pytest.raises(RuntimeError):
            call()
    monkeypatch.setattr(lib, "clock", lambda: time.time() + 10 * lib.PRUNE_GRACE_SECONDS)
    with lib.book_lock(HINTED):
        first = lib.current_name(HINTED)
        version = lib.new_version(HINTED)
        for name in ("pages.json", "tree.json", "meta.json"):
            shutil_copy = (lib.data_dir(HINTED) / name).read_bytes()
            (version / name).write_bytes(shutil_copy)
        lib.publish_version(HINTED, version)
        assert lib.current_name(HINTED) == version.name
        lib.prune_versions(HINTED)                            # keeps the pointer it reads now, and the one before
        assert version_names(HINTED) == sorted([first, version.name])
        (lib.book_dir(HINTED) / "CURRENT").write_text(first + "\n")   # the pointer moved back: prune follows it
        lib.prune_versions(HINTED)
        assert lib.current_name(HINTED) == first and first in version_names(HINTED)
        lib.discard_unpublished(HINTED, version)              # the pointer never named it now: removed
        assert version.name not in version_names(HINTED)
