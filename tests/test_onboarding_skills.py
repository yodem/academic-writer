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
    "PageIndex (a library on your own server)",
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
    assert "pageindex_command" in setup and "Never ask for a host" in setup
    assert not INSTALL_RE.search(setup.split("### 4g.")[1].split("## Step 5")[0])  # nothing to install
    trouble = (SKILLS / "setup" / "references" / "troubleshooting.md").read_text(encoding="utf-8")
    for heading in ("PageIndex not reachable", "Wrong book list", "Shadow errors in the report"):
        assert f"**{heading}**" in trouble, heading
    assert "aw\" library status --check" in trouble


def test_library_route_detection_honours_an_existing_library_json_and_never_overwrites_it():
    section = REFERENCE.read_text(encoding="utf-8").split("## Library route")[1]
    detect = section.split("### Detect")[1].split("### Ask")[0]
    # same resolution order as loadLibraryConfig: env, then library.json pageindex.command, then pilib
    assert "AW_PAGEINDEX_COMMAND" in detect and ".academic-helper/library.json" in detect
    assert "'pageindex'" in detect and "'command'" in detect and "'pilib'" in detect
    assert detect.index("env_cmd or file_cmd or 'pilib'") > 0
    assert "CURRENT_ROUTE" in detect
    ask = section.split("### Ask")[1].split("### Write")[0]
    assert "never overwritten without asking" in ask
    assert "(current)" in ask and "write nothing" in ask
    assert "do not ask and do not change the file" in ask  # route includes PageIndex but it is unreachable
    assert "only when there is no `library.json` yet" in ask


def test_detection_snippet_runs_and_follows_the_config_precedence(tmp_path):
    import subprocess
    section = REFERENCE.read_text(encoding="utf-8").split("## Library route")[1]
    code = re.search(r"python3 - <<'PY'\n(.*?)\nPY", section, re.S).group(1)

    def detect(cfg, env):
        proj = tmp_path / str(abs(hash((json.dumps(cfg), json.dumps(env)))))
        (proj / ".academic-helper").mkdir(parents=True)
        if cfg is not None:
            (proj / ".academic-helper" / "library.json").write_text(json.dumps(cfg))
        base = {"PATH": "/usr/bin:/bin"}
        out = subprocess.run(["python3", "-c", code], cwd=proj, env={**base, **env}, capture_output=True, text=True, check=True)
        return out.stdout.splitlines()

    assert detect(None, {}) == ["PAGEINDEX_NOT_CONFIGURED", "CURRENT_ROUTE=none CURRENT_PRIMARY=trove"]
    assert detect({"route": "both", "primary": "pageindex", "pageindex": {"command": "/path/to/wrapper"}}, {}) == [
        "PAGEINDEX_CONFIGURED", "CURRENT_ROUTE=both CURRENT_PRIMARY=pageindex"]
    assert detect(None, {"AW_PAGEINDEX_COMMAND": "pilib"})[0] == "PAGEINDEX_CONFIGURED"
    assert detect({"route": "trove"}, {})[0] == "PAGEINDEX_NOT_CONFIGURED"
