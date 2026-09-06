"""Phase 2 migration contract tests: AUDIT_MODE additive input on section-writer,
and the write skill's Workflow-tool wiring / interactive-planning-phase guarantee.

See docs/audits/2026-09-02-workflow-migration-spec.md section 6 for the contract
this test file enforces.
"""
import re
from pathlib import Path

SECTION_WRITER = Path("src/agents/section-writer.md")
WRITE_SKILL = Path("src/skills/write/SKILL.md")
SUBAGENT_START_HOOK = Path("src/hooks/src/lifecycle/subagent-start.ts")


def _input_section_text(text):
    """Slice out just the '## Input' section (up to the next top-level '## ' heading)."""
    match = re.search(r"^## Input\n(.*?)(?=^## )", text, re.DOTALL | re.MULTILINE)
    assert match, "section-writer.md must have a '## Input' heading"
    return match.group(1)


def test_section_writer_input_section_documents_audit_mode_external_value():
    text = SECTION_WRITER.read_text(encoding="utf-8")
    input_section = _input_section_text(text)
    assert "AUDIT_MODE" in input_section
    assert '"external"' in input_section or "`external`" in input_section
    # The external value must document that the orchestrator/script owns the
    # citation-audit gate and that the agent must not spawn the auditor itself.
    assert "MUST NOT spawn" in input_section
    # ...and that the agent returns its drafted paragraphs for the script to audit.
    assert "return" in input_section.lower()
    assert "unaudited" in input_section.lower()


def test_section_writer_input_section_documents_in_agent_fallback_as_default():
    text = SECTION_WRITER.read_text(encoding="utf-8")
    input_section = _input_section_text(text)
    # The in-agent path must be documented, within the AUDIT_MODE bullet itself,
    # as the preserved default/fallback — not a removed behavior.
    assert "AUDIT_MODE" in input_section
    assert "default" in input_section.lower()
    assert "additive" in input_section.lower()


def test_section_writer_still_has_input_and_output_headings():
    text = SECTION_WRITER.read_text(encoding="utf-8")
    assert "## Input" in text
    assert "## Output" in text


def test_section_writer_audit_mode_supersedes_fallback_and_behavioral_contract():
    # Guards against the file contradicting itself: AUDIT_MODE must be
    # documented as overriding both the fallback path's own Skill 8 auditor
    # spawn and the Persistent Behavioral Contract's gate 2, not just Step D.
    text = SECTION_WRITER.read_text(encoding="utf-8")
    assert "supersedes" in text.lower()
    assert "orthogonal to" in text.lower() and "geminiFallback" in text


def test_section_writer_input_section_forbids_silent_hand_draft_on_direct_spawn():
    # A direct Agent-tool spawn (no write-sections.js orchestrator) that omits
    # `unit`/`AUDIT_MODE` was observed hand-drafting a paragraph -- skipping
    # BOTH the Gemini path and the auditor citation gate -- with the omission
    # surfaced only in prose the caller might not read. AUDIT_MODE absent is
    # documented (above) as "preserve in-agent auditor behavior", not as
    # "skip the pipeline", so this guards the gap between what was documented
    # and what the agent actually did.
    text = SECTION_WRITER.read_text(encoding="utf-8")
    input_section = _input_section_text(text)
    assert "Direct spawn without orchestrator context" in input_section
    assert "is not license to skip the pipeline" in input_section
    assert "worst outcome this agent can produce" in input_section
    # The escape hatch must be an explicit STOP-and-report, not a silent
    # downgrade to unaudited prose.
    assert "STOP and report back" in input_section


def test_write_skill_names_write_sections_workflow_script():
    text = WRITE_SKILL.read_text(encoding="utf-8")
    assert "workflows/write-sections.js" in text


def test_write_skill_still_describes_planning_phase_as_interactive_and_human_approved():
    text = WRITE_SKILL.read_text(encoding="utf-8")
    assert "PHASE 1: CONVERSATIONAL" in text
    assert "human-in-the-loop" in text
    # A string that only exists because the outline-approval human gate (SPC-03)
    # is still described in prose — not satisfiable by the Phase 2 preamble alone.
    assert "Iterate until the researcher says" in text
    assert "Do NOT proceed to Step 6 until all four checks pass" in text


def test_write_skill_documents_workflow_absent_sequential_fallback():
    text = WRITE_SKILL.read_text(encoding="utf-8")
    assert "Fallback when the Workflow tool is unavailable" in text
    assert "AUDIT_MODE: external" in text
    assert "control flow only is duplicated" in text


def test_write_skill_notes_15_agent_dynamic_workflow_size_guideline():
    text = WRITE_SKILL.read_text(encoding="utf-8")
    assert "15-agent" in text
    assert "/config" in text
    assert "plugin cannot" in text.lower()


def test_subagent_start_hook_matches_academic_writer_auditor_agent_type():
    text = SUBAGENT_START_HOOK.read_text(encoding="utf-8")
    assert "academic-writer:auditor" in text
