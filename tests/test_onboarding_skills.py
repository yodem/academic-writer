"""Structural checks for the onboarding skills (setup, init, health).

The onboarding promise to a non-technical researcher is: Claude asks before it installs
anything, the Gemini key is never pasted into chat, and the key instructions match what the
code actually does (plugin setting kept in the OS keychain, bridged to GOOGLE_API_KEY).
These checks are deterministic text rules over the SKILL.md sources.
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / "src" / "skills"
MAX_LINES = 500

# An install command Claude would run: pip/pip3/python -m pip, brew, apt/apt-get, winget, npm.
INSTALL_RE = re.compile(
    r"\b(?:pip3?|python3?\s+-m\s+pip|brew|apt(?:-get)?|winget|npm)\s+(?:install|tap)\b"
)
HEADING_RE = re.compile(r"^#{2,6}\s")
ASK = "AskUserQuestion"


def _text(skill: str) -> str:
    return (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")


def _steps(text: str) -> list[list[str]]:
    """Split a SKILL.md into steps at every markdown heading (## .. ######) outside code fences."""
    steps: list[list[str]] = [[]]
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and HEADING_RE.match(line):
            steps.append([])
        steps[-1].append(line)
    return steps


def install_violations(text: str) -> list[str]:
    """Install command lines that are not preceded by an AskUserQuestion in the same step.

    Checked lines: every line inside a fenced code block, plus any prose line that *starts*
    with an install command. Inline prose mentions (e.g. a `! sudo apt install ...` the
    researcher types themselves) are instructions to the human, not commands Claude runs.
    """
    bad = []
    for step in _steps(text):
        asked = False
        in_fence = False
        for line in step:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            is_cmd = INSTALL_RE.search(stripped) and (
                in_fence or INSTALL_RE.match(stripped.lstrip("$! "))
            )
            if is_cmd and not asked:
                bad.append(f"{step[0].strip()} :: {stripped}")
            if ASK in line:
                asked = True
    return bad


def test_setup_and_init_ask_before_every_install():
    for skill in ("setup", "init"):
        text = _text(skill)
        assert INSTALL_RE.search(text), f"{skill}: expected at least one install step"
        assert install_violations(text) == [], f"{skill}: {install_violations(text)}"


def test_install_rule_catches_a_planted_bad_example():
    planted = (
        "## Step 4 — Python tools\n\n"
        "Install the packages:\n\n"
        "```bash\npip3 install python-docx\n```\n\n"
        "```python\nAskUserQuestion(questions=[])\n```\n"
    )
    assert install_violations(planted), "install before AskUserQuestion must be flagged"
    # A question in an *earlier* step does not cover a later step's install.
    earlier = (
        "## Step 1\n\n```python\nAskUserQuestion(questions=[])\n```\n\n"
        "## Step 2\n\n```bash\nbrew install hspell\n```\n"
    )
    assert install_violations(earlier), "a question from another step must not count"
    good = (
        "## Step 4\n\n```python\nAskUserQuestion(questions=[])\n```\n\n"
        "```bash\npython3 -m pip install --user python-docx\n```\n"
    )
    assert install_violations(good) == []


def test_setup_gemini_key_instructions_match_the_code():
    text = _text("setup")
    assert "https://aistudio.google.com/apikey" in text
    assert "/plugin" in text and "Configure" in text and "google_api_key" in text
    assert "keychain" in text
    assert '"${CLAUDE_PLUGIN_ROOT}/bin/aw" models check' in (
        SKILLS / "setup" / "references" / "gemini-key.md"
    ).read_text(encoding="utf-8")


def test_setup_never_asks_for_the_key_in_chat():
    text = _text("setup")
    assert "Never ask for the Gemini key in the chat" in text
    for skill in ("setup", "init"):
        for path in [SKILLS / skill / "SKILL.md", *(SKILLS / skill / "references").glob("*.md")]:
            body = path.read_text(encoding="utf-8")
            # The old flow said "ask them to paste the key" (into chat); pasting into the
            # /plugin Configure field is fine.
            assert not re.search(
                r"ask (?:them|the (?:user|researcher)) to paste|paste (?:the|your) key (?:here|below|in(?:to)? (?:the )?chat)",
                body, re.I), path
            # secrets.json is not a key source for aw (src/cli/tests/gemini.test.ts).
            assert "Project-local secrets file" not in body, path


def test_setup_has_no_developer_known_gap_note():
    assert "Known gap" not in _text("setup")
    assert "Known gap" not in (SKILLS / "setup" / "references" / "python-deps.md").read_text(
        encoding="utf-8"
    )


def test_setup_and_init_offer_the_intro_guide():
    for skill in ("setup", "init"):
        assert "/academic-writer:intro" in _text(skill), skill


def test_onboarding_skills_stay_under_500_lines():
    for skill in ("setup", "init", "health"):
        n = len(_text(skill).splitlines())
        assert n <= MAX_LINES, f"{skill}/SKILL.md has {n} lines"


def test_no_removed_gemini_mcp_tool_in_onboarding():
    for skill in ("setup", "init", "health"):
        for path in (SKILLS / skill).rglob("*.md"):
            assert "gemini_raw" not in path.read_text(encoding="utf-8"), path


def test_write_voice_gate_lets_a_first_time_author_through():
    """A new author has no voice store and no AUTHOR_VOICE.md. /write must check the
    store /voice actually writes, and offer to continue rather than dead-end."""
    text = (ROOT / "src" / "skills" / "write" / "SKILL.md").read_text(encoding="utf-8")
    gate = text.split("<!-- BEGIN voice-precondition-gate -->")[1].split("<!-- END voice-precondition-gate -->")[0]
    assert "${CLAUDE_PLUGIN_DATA}/voice" in gate
    assert "VOICE_MISSING" in gate and "AskUserQuestion" in gate
    assert "Write without it" in gate and "voice migrate" in gate


# --- Library route (Trove | PageIndex | both) and the PageIndex plugin setting -------------------

REFERENCE = SKILLS / "init" / "references" / "integration-setup.md"
ROUTE_LABELS = (
    "Trove (your current library)",
    "PageIndex (a second library: on this computer or your own server)",
    "Both: one answers and the other is tested quietly in the background",
)


def test_library_route_questions_are_plain_and_complete():
    ref = REFERENCE.read_text(encoding="utf-8")
    section = ref.split("## Library route")[1]
    assert "AskUserQuestion" in section
    for label in ROUTE_LABELS:
        assert label in section, label
    assert "Trove (recommended)" in section  # with Both, Trove answers by default
    assert "PAGEINDEX_NOT_CONFIGURED" in section and "pageindex_command" in section
    assert ".academic-helper/library.json" in section
    # no host, key or password is ever asked for in chat
    assert "Never ask for a host" in section


def test_init_and_update_tools_ask_the_library_route_question():
    for skill in ("init", "update-tools"):
        text = _text(skill)
        assert "AskUserQuestion" in text and ".academic-helper/library.json" in text, skill
        assert "PageIndex" in text and "references/integration-setup.md" in text, skill
        assert "Never install anything for this step" in text, skill
    # init keeps the question out of --quick mode (Phase 3 is skipped there)
    assert "no `library.json` is written" in _text("init")
    # update-tools never touches the profile for this step, and its description keeps its trigger phrase
    text = _text("update-tools")
    assert "does not touch `profile.md`" in text
    assert re.search(r"\bUse when\b", text.split("---")[1])


def test_library_route_examples_match_the_config_schema():
    schema = json.loads((ROOT / "src" / "schemas" / "library-config.schema.json").read_text(encoding="utf-8"))
    props = schema["properties"]
    ref = REFERENCE.read_text(encoding="utf-8").split("### Write")[1]
    blocks = re.findall(r"```json\n(.*?)\n```", ref, re.S)
    assert len(blocks) == 3
    for block in blocks:
        data = json.loads(block)
        assert set(data) <= set(props) and data["route"] in props["route"]["enum"], block
        if "primary" in data:
            assert data["primary"] in props["primary"]["enum"], block


def test_pageindex_setting_is_non_sensitive_and_bridged_without_a_host():
    manifest = json.loads((ROOT / "manifests" / "academic-writer.json").read_text(encoding="utf-8"))
    option = manifest["userConfig"]["pageindex_command"]
    assert option["sensitive"] is False and option["required"] is False and option["type"] == "string"
    assert "pilib" in option["description"] and "/path/to/" in option["description"]
    assert "://" not in option["description"] and "@" not in option["description"]  # no URL, no user@host
    hooks = (ROOT / "src" / "hooks" / "hooks.json").read_text(encoding="utf-8")
    assert "pageindex_command" not in hooks  # never interpolated into the shell-form command
    env_hook = (ROOT / "src" / "hooks" / "src" / "lifecycle" / "session-env.ts").read_text(encoding="utf-8")
    assert "AW_PAGEINDEX_COMMAND" in env_hook and "CLAUDE_PLUGIN_OPTION_PAGEINDEX_COMMAND" in env_hook


def test_setup_points_to_the_pageindex_setting_and_troubleshooting_covers_it():
    setup = _text("setup")
    assert "pageindex_command" in setup and "references/pageindex.md" in setup
    # the install itself lives in the reference, behind AskUserQuestion and --yes; the SKILL text installs nothing
    assert "Never ask for a host" in (SKILLS / "setup" / "references" / "pageindex.md").read_text(encoding="utf-8")
    assert not INSTALL_RE.search(setup.split("### 4g.")[1].split("## Step 5")[0])
    trouble = (SKILLS / "setup" / "references" / "troubleshooting.md").read_text(encoding="utf-8")
    for heading in ("PageIndex not reachable", "Wrong book list", "Shadow errors in the report"):
        assert f"**{heading}**" in trouble, heading
    assert "aw\" library status --check" in trouble


def test_library_route_detection_honours_an_existing_library_json_and_never_overwrites_it():
    section = REFERENCE.read_text(encoding="utf-8").split("## Library route")[1]
    detect = section.split("### Detect")[1].split("### Ask")[0]
    # the plugin resolves the command itself (env, library.json, built-in helper, pilib): no path probing in a quoted heredoc
    assert "AW_PAGEINDEX_COMMAND" in detect and ".academic-helper/library.json" in detect
    assert '"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" library status' in detect
    assert "pageindex_source" in detect and "'installed'" in detect and "'pilib'" in detect
    assert "CURRENT_ROUTE" in detect
    heredocs = re.findall(r"<<'PY'\n(.*?)\nPY", detect, re.S)
    assert heredocs and all("CLAUDE_PLUGIN_DATA" not in body and "${" not in body for body in heredocs)
    # the flags used exist in the CLI
    cli = (ROOT / "src" / "cli" / "src" / "library" / "cli.ts").read_text(encoding="utf-8")
    assert "subcommand === 'status'" in cli and "pageindex_source" in cli
    ask = section.split("### Ask")[1].split("### Write")[0]
    assert "never overwritten without asking" in ask
    assert "(current)" in ask and "write nothing" in ask
    # a PageIndex route that cannot be reached still offers the way out: switch to Trove, keep is the default
    unreachable = ask.split("includes PageIndex but detection says it is not configured")[1].split("**PageIndex not configured**")[0]
    assert "AskUserQuestion" in unreachable and "Switch this article to Trove" in unreachable
    assert '"label": "Keep it as it is"' in unreachable and '"label": "Switch to Trove"' in unreachable
    assert unreachable.index('"Keep it as it is"') < unreachable.index('"Switch to Trove"')  # keep listed first
    assert '"Keep it as it is" is the default' in unreachable and "unless the researcher explicitly picks" in unreachable
    assert "do not change the file" not in ask
    trouble = (SKILLS / "setup" / "references" / "troubleshooting.md").read_text(encoding="utf-8")
    assert "Switch to Trove" in trouble and "Keep it as it is" in trouble
    assert "Keep it as it is" in _text("update-tools") and "switch this" in _text("update-tools")
    assert "only when there is no `library.json` yet" in ask


def test_detection_snippet_reads_the_status_json_the_cli_prints(tmp_path):
    import subprocess
    section = REFERENCE.read_text(encoding="utf-8").split("## Library route")[1]
    code = re.search(r"python3 - <<'PY'\n(.*?)\nPY", section, re.S).group(1)
    status_path = "/tmp/aw-library-status.json"
    assert status_path in section and status_path in code

    def detect(status):
        sample = tmp_path / f"status-{abs(hash(json.dumps(status)))}.json"
        sample.write_text(json.dumps(status))
        out = subprocess.run(["python3", "-c", code.replace(status_path, str(sample))],
                             env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, check=True)
        return out.stdout.splitlines()

    assert detect({"route": "trove", "primary": "trove", "configured": False, "pageindex_source": "default", "installed": {"installed": False}}) == [
        "PAGEINDEX_NOT_CONFIGURED", "CURRENT_ROUTE=none CURRENT_PRIMARY=trove"]
    assert detect({"route": "both", "primary": "pageindex", "configured": True, "pageindex_source": "library.json"}) == [
        "PAGEINDEX_CONFIGURED", "CURRENT_ROUTE=both CURRENT_PRIMARY=pageindex"]
    assert detect({"route": "trove", "primary": "trove", "configured": False, "pageindex_source": "setting"})[0] == "PAGEINDEX_CONFIGURED"
    # a helper installed in this very session counts, with no environment variable involved
    assert detect({"route": "trove", "primary": "trove", "configured": True, "pageindex_source": "installed", "installed": {"installed": True, "tier": "core"}}) == [
        "PAGEINDEX_CONFIGURED", "CURRENT_ROUTE=trove CURRENT_PRIMARY=trove"]
    assert detect({"route": "trove", "configured": True, "pageindex_source": "default", "installed": {"installed": True}})[0] == "PAGEINDEX_CONFIGURED"
    assert detect({"route": "trove", "configured": True})[0] == "PAGEINDEX_NOT_CONFIGURED"


# --- Built-in PageIndex helper (Trove stays the default), library-eval ---------------------------

PAGEINDEX_REF = SKILLS / "setup" / "references" / "pageindex.md"


def test_pageindex_offer_is_asked_explained_and_trove_stays_the_default():
    text = PAGEINDEX_REF.read_text(encoding="utf-8")
    assert ASK in text
    for label in ("Set it up on this computer", "I run my own PageIndex on a server", "Not now"):
        assert f'"label": "{label}"' in text, label
    # the plan is shown before anything changes, and the install is behind a yes
    assert "library install --dry-run" in text
    assert text.index(ASK) < text.index("library install --yes")
    assert text.index("library install --dry-run") < text.index("library install --yes")
    assert "refuses to run without `--yes`" in text
    # what it is, what is sent to Google, how big and how long, in plain words
    for words in ("sent once to Google", "approx_size_mb", "a few minutes", "Trove stays your main library"):
        assert words in text, words
    # own server: setting only, placeholder path, nothing secret in chat or files
    assert "pageindex_command" in text and "/path/to/pilib-wrapper" in text
    assert "Never ask for a host, address, key or password in chat" in text
    assert "never put one in a file" in text
    assert "does not send your Gemini key to a server" in text
    # old Python is explained, not silently fixed
    assert "Python 3.10 or newer" in text and "Do not install Python" in text
    # backfill reads Trove only, shows the plan and the estimate first
    assert "library backfill --shelf-current --skip-existing --dry-run" in text


def test_the_skills_that_offer_pageindex_point_at_the_one_reference():
    for skill in ("setup", "init", "update-tools"):
        assert "setup/references/pageindex.md" in _text(skill) or "references/pageindex.md" in _text(skill), skill
    assert "Trove stays the default" in _text("setup") or "Trove is the default" in _text("setup")
    assert "Never install without" in _text("setup")
    health = _text("health")
    for words in ("pageindex_source", "installed.tier", "matches_pinned", "index_trove", "never install from here"):
        assert words in health, words
    assert "Never install anything for this step" in _text("init")
    assert "Never install anything for this step" in _text("update-tools")
    integration = REFERENCE.read_text(encoding="utf-8")
    assert "built-in helper" in integration and "installed" in integration and "AW_PAGEINDEX_HOME" not in integration
    assert "pageindex_command" in json.dumps(json.loads((ROOT / "manifests" / "academic-writer.json").read_text(encoding="utf-8")))


def test_pageindex_command_setting_says_the_built_in_helper_is_the_fallback():
    manifest = json.loads((ROOT / "manifests" / "academic-writer.json").read_text(encoding="utf-8"))
    description = manifest["userConfig"]["pageindex_command"]["description"] if "userConfig" in manifest else None
    if description is None:
        description = json.dumps(manifest)
    assert "built-in PageIndex helper" in description
    assert "wins over the built-in helper" in description


def test_onboarding_and_ingest_skills_stay_under_500_lines():
    for skill in ("setup", "init", "health", "update-tools", "library-eval", "ingest", "ingest-book", "ocr"):
        n = len(_text(skill).splitlines())
        assert n <= MAX_LINES, f"{skill}/SKILL.md has {n} lines"


def test_no_skill_text_inlines_a_threshold_or_a_key():
    for skill in ("setup", "init", "update-tools", "library-eval", "ingest", "ingest-book", "ocr"):
        for path in [SKILLS / skill / "SKILL.md", *(SKILLS / skill / "references").glob("*.md")]:
            body = path.read_text(encoding="utf-8")
            assert not re.search(r"AIza[0-9A-Za-z_-]{10,}", body), path
            assert "--api-key" not in body, path
            assert not re.search(r"\b(?:askAboveCalls|maxCalls|minPairs)\b\s*[:=]\s*\d", body), path


LIBRARY_EVAL = SKILLS / "library-eval" / "SKILL.md"


def test_library_eval_skill_is_invocable_and_registered():
    import yaml

    text = LIBRARY_EVAL.read_text(encoding="utf-8")
    fm = yaml.safe_load(re.match(r"---\n(.*?)\n---\n", text, re.S).group(1))
    assert fm["name"] == "library-eval" and fm["user-invocable"] is True
    assert "Use when" in fm["description"] and len(fm["description"]) <= 1024
    meta = fm["metadata"]
    assert meta.get("author") and meta.get("version") and meta.get("summary")
    assert "AskUserQuestion" in fm["allowed-tools"]
    gen = (ROOT / "scripts" / "gen-guide.py").read_text(encoding="utf-8")
    assert '"library-eval"' in gen
    assert "/academic-writer:library-eval" in (SKILLS / "help" / "SKILL.md").read_text(encoding="utf-8")
    assert "/academic-writer:library-eval" in (ROOT / "src" / "guide" / "index.html").read_text(encoding="utf-8")


def test_library_eval_runs_the_steps_in_order_and_keeps_the_blinding():
    text = LIBRARY_EVAL.read_text(encoding="utf-8")
    steps = [text.index(f"library eval {step}") for step in ("plan", "run", "pairs", "page", "import", "unblind")]
    assert steps == sorted(steps), steps
    assert "eval status" in text
    # asked before anything is spent and before anything is published
    assert text.index(ASK) < text.index("library eval run")
    assert "estimated_usd" in text and "go to Anthropic" in text
    assert "ask first" in text and "claude.ai" in text
    # blinding rules for the orchestrating model
    assert "sealed/" in text and "Do not open" in text
    assert "--force" in text and "Never add `--force`" in text
    assert "you must not turn it into" in text
    # the judging page is a local file by default and the import shape is given
    assert "judge.html" in text and "Download judgments" in text
    assert '"verdict": "A|B|same|neither|skip"' in text
    assert "--partial" in text
    # claims and Anthropic/OpenAI data flow are stated; no key is ever requested
    assert "OpenAI" in text and "GOOGLE_API_KEY" not in text


def test_no_skill_moves_pages_to_another_ocr_engine_without_asking():
    engines = (SKILLS / "ocr" / "references" / "engines.md").read_text(encoding="utf-8")
    for path in (SKILLS / "ocr" / "SKILL.md", SKILLS / "ingest-book" / "SKILL.md", SKILLS / "ocr" / "references" / "engines.md"):
        body = path.read_text(encoding="utf-8")
        assert not re.search(r"escalat\w* (?:those |these |the )?pages? to Gemini", body, re.I), path
        assert "Gemini is the escalation" not in body and "with Gemini for pages" not in body, path
        assert "Gemini" in body and "AskUserQuestion" in body and "text goes to Google" in body, path
    assert "Never send a page to Gemini" in engines and "on your own" in engines
    assert "OCR, not image-verified" in engines
    assert "The same rule applies to every switch of engine" in engines
