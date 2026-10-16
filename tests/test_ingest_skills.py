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


# --- PageIndex dual-write, adding to an existing item, OCR engines -------------------------------

import re  # noqa: E402

REFS = ROOT / "src/skills/ingest/references"
OCR = ROOT / "src/skills/ocr/SKILL.md"
ENGINES = ROOT / "src/skills/ocr/references/engines.md"
CLI = ROOT / "src/cli/src/library/cli.ts"
EVAL_CLI = ROOT / "src/cli/src/library/eval/cli.ts"
ABS_AW = '"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD"'

# Skills and references that tell Claude to run `aw library ...`; every command in a code block is checked.
LIBRARY_COMMAND_FILES = [
    INGEST, INGEST_BOOK, REFS / "index-for-pageindex.md", REFS / "existing-item.md",
    ROOT / "src/skills/setup/references/pageindex.md", ROOT / "src/skills/library-eval/SKILL.md",
    ROOT / "src/skills/setup/references/troubleshooting.md",
]


def _code_blocks(text):
    """The bodies of the shell code fences of a markdown text (python and json fences are skipped)."""
    blocks, current, language = [], None, ""
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            if current is None:
                current, language = [], line.lstrip()[3:].strip()
            else:
                if language in ("", "bash", "sh"):
                    blocks.append("\n".join(current))
                current = None
        elif current is not None:
            current.append(line)
    return blocks


def _library_commands(path):
    """(subcommand, [flags]) for every `... library <sub> ...` command inside a code fence of the file."""
    text = _read(path)
    commands = []
    for block in _code_blocks(text):
        joined = re.sub(r"\\\n\s*", " ", block)
        for line in joined.splitlines():
            match = re.search(r'bin/aw"\s.*?\blibrary\s+(\w+)(?:\s+(plan|run|pairs|page|import|unblind|status))?(.*)$', line)
            if match:
                commands.append((match.group(1), match.group(2), re.findall(r"(--[a-z][a-z-]*)", match.group(3)), line))
    return commands


def test_skills_pin_the_library_commands_to_the_cli():
    cli, eval_cli = _read(CLI), _read(EVAL_CLI)
    subcommands = set(re.search(r"expected aw library ([\w|]+)'", cli).group(1).split("|"))
    eval_subs = set(re.search(r"const SUBCOMMANDS = \[(.*?)\]", eval_cli).group(1).replace("'", "").replace(" ", "").split(","))
    eval_flags = set(re.findall(r"'(--[a-z-]+)'", re.search(r"const BOOLEAN_FLAGS = new Set\(\[(.*?)\]\)", eval_cli).group(1)
                                + re.search(r"const VALUE_FLAGS = new Set\(\[(.*?)\]\)", eval_cli).group(1)))
    seen = set()
    for path in LIBRARY_COMMAND_FILES:
        for sub, eval_sub, flags, line in _library_commands(path):
            assert sub in subcommands, f"{path.name}: unknown library subcommand {sub}: {line}"
            seen.add(sub)
            if sub == "eval":
                assert eval_sub in eval_subs, f"{path.name}: unknown eval step: {line}"
                for flag in flags:
                    assert flag in eval_flags, f"{path.name}: eval has no {flag}: {line}"
            else:
                for flag in flags:
                    assert f"'{flag}'" in cli, f"{path.name}: `library {sub}` has no {flag}: {line}"
    assert {"index", "install", "backfill", "status", "eval"} <= seen


def test_every_library_command_uses_the_absolute_aw_path_and_data_dir():
    for path in LIBRARY_COMMAND_FILES:
        for sub, _eval, _flags, line in _library_commands(path):
            assert '"${CLAUDE_PLUGIN_ROOT}/bin/aw"' in line, f"{path.name}: {line}"
            if sub in {"index", "install", "backfill", "uninstall"}:
                assert '--data-dir "${CLAUDE_PLUGIN_DATA}"' in line, f"{path.name}: {line}"


def test_ingest_skills_index_for_pageindex_after_the_read_back():
    ingest, book = _read(INGEST), _read(INGEST_BOOK)
    for text in (ingest, book):
        assert "library index" in text and "--trove-id <BOOK_ID>" in text
        assert "references/index-for-pageindex.md" in text
        assert "never undoes it" in text  # the Trove upload is finished first and stays valid
        assert "Ask first" in text
    assert ingest.index("## 6. Read-back") < ingest.index("## 7. Index for PageIndex")
    assert book.index("### Phase D") < book.index("### Phase E")
    # the article ingest also writes the table-of-contents metadata PageIndex builds its outline from
    assert "--toc" in ingest and "page 1" in ingest.lower()


def test_index_reference_asks_with_an_estimate_before_sending_text_to_google():
    text = _read(REFS / "index-for-pageindex.md")
    assert "AskUserQuestion" in text
    assert text.index("--dry-run") < text.index("--summaries gemini|hints|none")
    for field in ("expected_calls", "input_chars", "hinted_entries", "fallback", "needs --yes"):
        assert field in text
    for words in ("sent to Google", "--summaries hints", "free", "Not now", "Trove copy is already safe"):
        assert words in text
    # fields the skill reads exist in the CLI's answer
    index_cmd = _read(ROOT / "src/cli/src/library/index-cmd.ts")
    for field in ("expected_calls", "input_chars", "hinted_entries", "fallback", "nodes_with_summary", "cost_usd"):
        assert f"'{field}'" in index_cmd, field
    assert "pilib.index_trove" in text and "index_trove" in _read(CLI)
    assert "key" in text.lower() and "Never ask for or show a key" in text


def test_existing_item_flow_appends_and_reapplies_the_table_of_contents_last():
    text = _read(REFS / "existing-item.md")
    assert "trove items append" in text and "--prepend" in text
    assert "trove items toc <ITEM_ID> --json" in text
    assert text.index("trove items append") < text.index("trove items enrich <ITEM_ID> --toc")
    assert "resets the whole table of contents" in text
    for check in ("Page count", "Old entries", "New entries", "byte-equal", "Printed-page markers"):
        assert check in text, check
    assert "library index --trove-id <ITEM_ID>" in text and "reuses the summaries" in text
    assert "Never delete or overwrite" in text and "--no-session" in text
    for skill in (_read(INGEST), _read(INGEST_BOOK)):
        assert "references/existing-item.md" in skill
        assert "trove items append" in skill and "trove items put" in skill


def test_put_page_one_is_followed_by_reapplying_the_toc_in_ingest_book():
    text = _read(INGEST_BOOK)
    assert "`put` makes Trove rebuild the whole table of contents" in text
    assert "last write to the book" in text


def test_ocr_options_cover_the_four_engines_in_both_ingest_skills_and_the_ocr_skill():
    for path in (INGEST, INGEST_BOOK, OCR):
        text = _read(path)
        for engine in ("Gemini", "Claude", "Codex", "Tesseract"):
            assert engine in text, f"{path.name}: {engine}"
        assert "references/engines.md" in text
        assert "AskUserQuestion" in text
        assert "OCR engine:" in text or "Record which engine" in text
        assert "never an external tool" not in text
    # the plugin's own reader stays the default and keeps its command
    for path in (INGEST, INGEST_BOOK, OCR):
        assert "ocr \\" in _read(path)
    engines = _read(ENGINES)
    assert "codex exec" in engines and " -i " in engines  # Codex reads images with -i
    assert "tesseract" in engines and "heb+eng" in engines
    assert "pdftoppm -r 150" in engines
    for rule in ("Never overwrite the source", "One page per call", "truncated", "orientation"):
        assert rule in engines, rule
    assert "AskUserQuestion" in engines


def test_ocr_skill_may_ask_the_engine_question():
    match = re.match(r"---\n(.*?)\n---\n", _read(OCR), re.S)
    import yaml
    fm = yaml.safe_load(match.group(1))
    assert "AskUserQuestion" in fm["allowed-tools"]
    assert "Use when" in fm["description"]
    assert fm["metadata"].get("summary")


def test_existing_item_read_back_compares_page_one_with_the_intended_text():
    text = _read(REFS / "existing-item.md")
    assert "approved replacement" in text and "/tmp/reading-guide.md" in text
    assert "never with the old text" in text
    assert "Old pages** 1 and 2 read back byte-equal" not in text
    assert "Checks 3 and 5" in text  # appended pages and merged table of contents checked in every case
