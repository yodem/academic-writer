"""Structural checks for the onboarding skills (setup, init, health).

The onboarding promise to a non-technical researcher is: Claude asks before it installs
anything, the Gemini key is never pasted into chat, and the key instructions match what the
code actually does (plugin setting kept in the OS keychain, bridged to GOOGLE_API_KEY).
These checks are deterministic text rules over the SKILL.md sources.
"""

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
