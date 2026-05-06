# Prevent Mikdashim-Style Writing Failures — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the eight failure modes from the 2026-05-02 mikdashim feedback session (`.academic-writer/feedback/2026-05-02-mikdash-ezra-nehemia-meta.md`) into deterministic gates so the next `/academic-writer:write` or `/academic-writer:edit` run in mikdashim — or any Hebrew project — cannot reproduce them.

**Architecture:** The plugin already has three deterministic enforcement surfaces — pattern reference (section-writer Skill 6), evidence map (deep-reader → architect handoff), and citation audit (auditor hard gate). The plan extends each surface to cover the new failure modes, then adds a precondition to `/academic-writer:write` that prevents inline rewrites after compaction.

**Tech Stack:** Markdown agent prompts, Markdown skill definitions, Bash glue, esbuild-bundled TypeScript hooks (no hook changes required), Python DOCX generator (unchanged).

**Prior work already landed (2026-05-02 feedback session, before this plan):**
- `plugins/academic-writer/skills/write/references/anti-ai-patterns-hebrew.md` — added 2 rows to Section A (`מבחינת` opener; first-paragraph opener must match `opening_formula`) and added Sections F (Editorial Meta-Summary), G (Unsourced Factual Assertions), H (Topic Drift & Padding). Mirrored to `src/skills/write/references/anti-ai-patterns-hebrew.md`.
- `~/.claude/projects/-Users-yotamfromm-dev-Academic-Helper/memory/feedback_enforcement_not_memory.md` and `feedback_deep_reader_chapter_enumeration.md` — captured plugin gaps for future agent prompt edits.
- `~/dev/bar-ilan/mikdashim/.academic-writer/feedback/2026-05-02-mikdash-ezra-nehemia-meta.md` — full session record.

**Failure modes addressed by this plan:**

| # | Failure | Fix surface |
|---|---|---|
| F1 | Article didn't open with profile `opening_formula` | Pattern ref Section A row (already added) + verification (Task 1) |
| F2 | Paragraph opened with `מבחינת` | Pattern ref Section A row (already added) + verification (Task 1) |
| F3 | Hallucinated `טכניקה מוכרת בארכיטקטורה הפרסית` (unsourced fact) | Pattern ref Section G + auditor hard-gate extension (Task 4) |
| F4 | Unprompted `ניתן ללמוד כי...` | Pattern ref Section F (already added) |
| F5 | Personnel counts when not asked | Pattern ref Section H (already added) |
| F6 | Filler `דמותו של עזרא מסכמת...` | Pattern ref Section F (already added) |
| F7 | Filler ending `הראוי לבחינה מדוקדקת` | Pattern ref Section F (already added) |
| F8 | Skipped Nehemiah 10 + 12 (didn't enumerate chapters) | Deep-reader chapter-enumeration step (Task 2) + architect coverage gate (Task 3) |
| F9 | Post-compaction wrote inline instead of re-invoking pipeline | Write skill precondition: existing-article guard (Task 5) |
| F10 | Researcher term aversions (`הכתוב מעיד`, `משרטטים`, `עת`) only in memory | Profile-driven banned-terms list (Task 6) + section-writer style check (Task 7) |

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `src/skills/write/references/anti-ai-patterns-hebrew.md` | Hebrew anti-AI pattern reference | (Already extended — Task 1 verifies enforcement) |
| `src/agents/deep-reader.md` | Source exploration → evidence map → sources.json | Task 2: add chapter-enumeration step |
| `src/agents/architect.md` | Thesis + outline proposal | Task 3: gate thesis on chapter-coverage field |
| `src/agents/auditor.md` | Citation hard gate | Task 4: extend to flag unsourced factual claims |
| `src/skills/write/SKILL.md` | Write pipeline orchestration | Task 5: add existing-article precondition |
| `src/agents/section-writer.md` | Per-paragraph 8-skill pipeline | Task 7: load profile `bannedTerms` in Skill 2 |
| `~/dev/bar-ilan/mikdashim/.academic-helper/profile.md` | Researcher profile | Task 6: add `bannedTerms` field |
| `tests/test_plugin_structure.py` | Structural integrity tests | Task 8: add regression tests covering F1–F10 |
| `plugins/academic-writer/...` | Build output | Task 9: rebuild via `npm run build` |

The plan edits `src/` (the source of truth per CLAUDE.md), then runs `npm run build` to copy into `plugins/`.

---

## Task 1: Verify pattern reference Sections A/F/G/H are picked up by section-writer

**Files:**
- Read: `plugins/academic-writer/agents/section-writer.md:354-410`
- Read: `plugins/academic-writer/skills/write/references/anti-ai-patterns-hebrew.md`
- Test: `tests/test_anti_ai_pattern_coverage.py` (NEW)

This task is verification-only — no behavioural change. The pattern reference was extended in the prior feedback session; we need to prove section-writer's Skill 6 actually reads the new sections.

- [ ] **Step 1.1: Read section-writer.md Skill 6 to confirm pattern-iteration is generic**

```bash
sed -n '354,410p' plugins/academic-writer/agents/section-writer.md
```

Expected: `cat plugins/academic-writer/skills/write/references/anti-ai-patterns-${LANG_LOWER}.md` followed by per-pattern cap sweep that iterates *every named pattern with a per-article cap*. If Skill 6 only iterates a hard-coded subset (e.g., only Sections A–E), record this as a bug and add Step 1.4 to generalise it.

- [ ] **Step 1.2: Write a structural regression test**

```python
# tests/test_anti_ai_pattern_coverage.py
"""Regression tests for the 2026-05-02 mikdashim failure modes."""
import re
from pathlib import Path

REF = Path("plugins/academic-writer/skills/write/references/anti-ai-patterns-hebrew.md")

def test_section_A_blocks_mibchinat_paragraph_opener():
    text = REF.read_text(encoding="utf-8")
    assert "מבחינת" in text
    assert "Per-paragraph cap: 0 as opener" in text

def test_section_A_enforces_opening_formula():
    text = REF.read_text(encoding="utf-8")
    assert "opening_formula" in text
    assert "במאמר זה" in text
    assert "Per-article cap: 0 violations" in text

def test_section_F_exists_with_meta_summary_patterns():
    text = REF.read_text(encoding="utf-8")
    assert "### F. Editorial Meta-Summary" in text
    for pat in [
        "מסכמ",            # X מסכמת את Y
        "ומכאן עולה",
        "הראוי לבחינה מדוקדקת",
        "ניתן ללמוד כי",
    ]:
        assert pat in text, f"missing F pattern: {pat}"

def test_section_G_hard_rule_present():
    text = REF.read_text(encoding="utf-8")
    assert "### G. Unsourced Factual Assertions" in text
    assert "Per-article cap: 0" in text
    assert "[NEEDS REVIEW: source for" in text

def test_section_H_blocks_quantitative_padding():
    text = REF.read_text(encoding="utf-8")
    assert "### H. Topic Drift & Padding" in text
    assert "מאה עשרים ושמונה משוררים" in text or "Quantitative trivia" in text
```

- [ ] **Step 1.3: Run the test to verify the pattern reference is in the expected shape**

```bash
python3 -m pytest tests/test_anti_ai_pattern_coverage.py -v
```

Expected: 5 PASSED.

- [ ] **Step 1.4: Commit**

```bash
git add tests/test_anti_ai_pattern_coverage.py
git commit -m "test: regression tests for mikdashim anti-AI patterns (Sections A/F/G/H)"
```

---

## Task 2: Add chapter-enumeration step to deep-reader

**Files:**
- Modify: `src/agents/deep-reader.md`
- Test: `tests/test_deep_reader_prompt.py` (NEW)

The deep-reader agent must detect "across all books" scoping in the assignment text and produce an explicit `chapter_coverage` field that lists every chapter in each cited book with a coverage status.

- [ ] **Step 2.1: Write the failing structural test**

```python
# tests/test_deep_reader_prompt.py
from pathlib import Path

DR = Path("src/agents/deep-reader.md")

def test_deep_reader_has_chapter_enumeration_trigger():
    text = DR.read_text(encoding="utf-8")
    # Must mention the trigger phrases that activate chapter enumeration
    assert "לאורך הספרים" in text or "across all books" in text or "across both books" in text
    assert "chapter_coverage" in text

def test_deep_reader_chapter_coverage_schema():
    text = DR.read_text(encoding="utf-8")
    # Each chapter row must record a status
    assert "covered" in text
    assert "skipped-irrelevant" in text
```

- [ ] **Step 2.2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_deep_reader_prompt.py -v
```

Expected: 2 FAILED — `chapter_coverage` not in deep-reader.md.

- [ ] **Step 2.3: Add the chapter-enumeration step to deep-reader.md**

Read `src/agents/deep-reader.md` and find the section that describes the evidence-mapping output (between Step 1b and the closing summary). Insert a new step:

````markdown
## Step 1c — Chapter Coverage Enumeration (when assignment scopes "across all books")

If the user-supplied assignment instruction text contains any of the trigger phrases:

- Hebrew: `לאורך הספרים`, `לאורך הספר`, `איתור הפרקים`, `בכל הפרקים`
- English: `across all books`, `across both books`, `throughout the book(s)`, `every relevant chapter`

then you MUST produce a `chapter_coverage` field in the evidence map. The field is a JSON object whose keys are book names (matching the `workTitle` field in `sources.json`) and whose values are arrays describing every chapter in that book.

Schema:

```json
{
  "chapter_coverage": {
    "Ezra": [
      { "chapter": 1,  "status": "covered",            "evidence_ids": ["ev_ezra1_cyrus_decree"] },
      { "chapter": 2,  "status": "skipped-irrelevant", "reason": "list of returnees only — no temple/personnel/cult content" },
      { "chapter": 3,  "status": "covered",            "evidence_ids": ["ev_ezra3_altar", "ev_ezra3_foundation"] }
    ],
    "Nehemiah": [
      { "chapter": 10, "status": "covered",            "evidence_ids": ["ev_neh10_covenant", "ev_neh10_wood_offering"] },
      { "chapter": 12, "status": "covered",            "evidence_ids": ["ev_neh12_high_priest_succession", "ev_neh12_wall_dedication"] }
    ]
  }
}
```

Rules:
1. **Every chapter in every named book must appear** with one of two statuses: `covered` (you read it and emitted at least one evidence record) or `skipped-irrelevant` (you read it and judged it not responsive to the assignment, with a one-line `reason`).
2. **No chapter may be silently omitted.** A missing chapter is a fail — the architect will reject the evidence map and re-spawn deep-reader.
3. **`evidence_ids` must reference records you actually emitted** in the evidence map. The architect cross-checks.
4. If the assignment does not contain any trigger phrase, the `chapter_coverage` field is optional. Default behaviour (curated reading) still applies for narrowly-scoped assignments.

This step is mandatory before Step 2 (the structured summary). The architect agent will reject your output if `chapter_coverage` is missing when the trigger phrases are present.
````

- [ ] **Step 2.4: Run the test to verify it passes**

```bash
python3 -m pytest tests/test_deep_reader_prompt.py -v
```

Expected: 2 PASSED.

- [ ] **Step 2.5: Commit**

```bash
git add src/agents/deep-reader.md tests/test_deep_reader_prompt.py
git commit -m "feat(deep-reader): chapter coverage enumeration when assignment scopes across all books"
```

---

## Task 3: Gate architect on chapter coverage

**Files:**
- Modify: `src/agents/architect.md`
- Test: `tests/test_architect_prompt.py` (NEW)

The architect agent receives the deep-reader's evidence map and proposes a thesis. After Task 2, that map MAY contain `chapter_coverage`. The architect must verify completeness before proposing — if any chapter is uncovered without justification, return the map to deep-reader rather than drafting a thesis.

- [ ] **Step 3.1: Write the failing structural test**

```python
# tests/test_architect_prompt.py
from pathlib import Path

A = Path("src/agents/architect.md")

def test_architect_checks_chapter_coverage():
    text = A.read_text(encoding="utf-8")
    assert "chapter_coverage" in text
    assert "reject" in text.lower() or "re-spawn" in text.lower() or "return to deep-reader" in text.lower()
```

- [ ] **Step 3.2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_architect_prompt.py -v
```

Expected: FAIL.

- [ ] **Step 3.3: Add the coverage gate to architect.md**

Find the section in `src/agents/architect.md` that describes how the architect consumes the deep-reader's output (typically near the top, before the thesis-proposal logic). Insert this block before the thesis-proposal step:

````markdown
## Coverage Pre-Check (before thesis proposal)

If the deep-reader's evidence map contains a `chapter_coverage` field, you MUST verify it before proposing a thesis. The check has three steps:

1. **Every chapter has a status.** Iterate every entry in every book. Any entry without `status: "covered"` or `status: "skipped-irrelevant"` (with a `reason`) is invalid.
2. **No silent gaps.** For each book in the evidence map, the chapter numbers must form a contiguous range from chapter 1 to the book's last chapter. Missing chapter numbers are fail.
3. **`evidence_ids` cross-check.** Every `evidence_ids` array must reference records that exist in the deep-reader's evidence map.

If any check fails:
- Do NOT propose a thesis.
- Emit a single message to the user listing the gaps (e.g., "Nehemiah chapter 10 is missing from chapter_coverage").
- Recommend the user re-run the deep-reader on the gap. (You cannot spawn deep-reader yourself; the orchestrator handles that.)

If `chapter_coverage` is absent and the assignment did not contain a trigger phrase (`לאורך הספרים`, `איתור הפרקים`, `across all books`, etc.), proceed to thesis proposal as normal.
````

- [ ] **Step 3.4: Run the test to verify it passes**

```bash
python3 -m pytest tests/test_architect_prompt.py -v
```

Expected: PASS.

- [ ] **Step 3.5: Commit**

```bash
git add src/agents/architect.md tests/test_architect_prompt.py
git commit -m "feat(architect): chapter-coverage gate before thesis proposal"
```

---

## Task 4: Extend auditor to flag unsourced factual claims (Section G)

**Files:**
- Modify: `src/agents/auditor.md`
- Test: `tests/test_auditor_prompt.py` (NEW)

Currently `auditor` checks that citations match `sources.json`. It does NOT check whether non-trivial factual sentences without a citation are sourced at all. Section G of the pattern reference declares this a hard rule (cap=0). Encode it in the auditor's gate.

- [ ] **Step 4.1: Write the failing structural test**

```python
# tests/test_auditor_prompt.py
from pathlib import Path

AUD = Path("src/agents/auditor.md")

def test_auditor_checks_unsourced_factual_claims():
    text = AUD.read_text(encoding="utf-8")
    # Must reference Section G + the [NEEDS REVIEW: source for ...] tag contract
    assert "Section G" in text or "Unsourced Factual" in text
    assert "[NEEDS REVIEW: source for" in text

def test_auditor_lists_factual_cue_categories():
    text = AUD.read_text(encoding="utf-8")
    # Must enumerate the cue categories the pattern ref names
    for cue in ["dating", "dimensions", "technique", "scholarly consensus"]:
        assert cue in text.lower(), f"missing factual-cue category: {cue}"
```

- [ ] **Step 4.2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_auditor_prompt.py -v
```

Expected: FAIL.

- [ ] **Step 4.3: Add Section G enforcement to auditor.md**

In `src/agents/auditor.md`, locate the "Checks" section that lists the citation accuracy checks (A, B, C, D). Add a new check E:

````markdown
### Check E — Unsourced Factual Assertions (Section G hard rule)

In addition to verifying that cited claims are accurate, scan every paragraph for **uncited factual claims** that should have a citation. The pattern reference (`anti-ai-patterns-${language}.md` Section G) declares this a per-article cap=0 rule.

**Detection cues — flag any sentence that:**
1. Asserts a **dating** ("בתקופה X", "במאה הY", "in the Nth century") without a citation.
2. Asserts **dimensions** or material specs ("60 אמה", "three courses of stone") that aren't a direct quote from a primary text in the assignment.
3. Asserts a **technique** is "well-known" / "characteristic of" / "typical of" / "מוכר ב..." / "מקובל ב..." without a citation.
4. Asserts **scholarly consensus** ("most scholars", "מקובל לחשוב", "ידוע בספרות") without naming the consensus.
5. Asserts **archaeological / material-culture** facts ("excavations show", "ממצאים מעידים") without a citation.

**Action:**
- If the claim CAN be supported from a quoted primary text in the assignment or from `sources.json`, emit a recommended citation in the audit report.
- If it cannot, mark the paragraph **REJECTED** and tag the offending sentence with `[NEEDS REVIEW: source for "<first 8 words of claim>"]`.
- The paragraph cannot pass the audit gate until every Section G violation is either cited or removed.

**Why this is a hard gate:** The 2026-05-02 mikdashim failure (sentence "טכניקה מוכרת בארכיטקטורה של התקופה הפרסית") was a Section G violation that the citation-accuracy check could not catch — there was no citation to verify because the claim was uncited. Section G closes that gap.
````

- [ ] **Step 4.4: Run the test to verify it passes**

```bash
python3 -m pytest tests/test_auditor_prompt.py -v
```

Expected: PASS.

- [ ] **Step 4.5: Commit**

```bash
git add src/agents/auditor.md tests/test_auditor_prompt.py
git commit -m "feat(auditor): hard-gate unsourced factual claims (Section G)"
```

---

## Task 5: Add existing-article precondition to /academic-writer:write

**Files:**
- Modify: `src/skills/write/SKILL.md`
- Test: `tests/test_write_skill_precondition.py` (NEW)

After context compaction, the model often continues writing inline instead of re-invoking the pipeline. Defensive precondition: if `articles/<slug>.md` already exists, route to `/academic-writer:edit` instead of overwriting.

- [ ] **Step 5.1: Write the failing structural test**

```python
# tests/test_write_skill_precondition.py
from pathlib import Path

WS = Path("src/skills/write/SKILL.md")

def test_write_skill_has_existing_article_precondition():
    text = WS.read_text(encoding="utf-8")
    # Must check whether the article already exists and route to edit
    assert "articles/" in text
    assert "academic-writer:edit" in text
    # Must mention the existence check
    assert "already exists" in text.lower() or "test -f" in text or "[ -f" in text
```

- [ ] **Step 5.2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_write_skill_precondition.py -v
```

Expected: FAIL.

- [ ] **Step 5.3: Add the precondition block to write/SKILL.md**

Find the very first step of the `/academic-writer:write` pipeline (Phase 1, "subject collection" or similar). Insert this block immediately after the skill loads the profile:

````markdown
## Pre-flight: existing-article guard

After computing the candidate slug from the user-supplied subject, check whether the article already exists:

```bash
SLUG="$(echo "$SUBJECT" | python3 -c "import sys,re; t=sys.stdin.read().strip().lower(); print(re.sub(r'[^a-z0-9]+', '-', t).strip('-')[:60])")"
MD_PATH="articles/${SLUG}.md"

if [ -f "$MD_PATH" ]; then
  echo "An article already exists at $MD_PATH."
  echo "Switching to edit mode — running /academic-writer:edit instead of overwriting."
  echo "If you intended to start over, delete $MD_PATH first."
  # Hand off to the edit skill rather than continuing the write pipeline.
  exit 0
fi
```

If the file exists, the skill MUST stop the write pipeline and tell the user to use `/academic-writer:edit articles/${SLUG}.md` (or `/academic-writer:edit-section` for a single section). Do NOT continue with deep-reader, architect, etc., because writing inline at that point produces ungated prose (the 2026-05-02 mikdashim post-compaction failure).

If the file does not exist, proceed with Phase 1 normally.
````

- [ ] **Step 5.4: Run the test to verify it passes**

```bash
python3 -m pytest tests/test_write_skill_precondition.py -v
```

Expected: PASS.

- [ ] **Step 5.5: Commit**

```bash
git add src/skills/write/SKILL.md tests/test_write_skill_precondition.py
git commit -m "feat(write): existing-article guard before pipeline entry"
```

---

## Task 6: Add bannedTerms to mikdashim profile

**Files:**
- Modify: `~/dev/bar-ilan/mikdashim/.academic-helper/profile.md`

Researcher term aversions (memory items 7–9 from `feedback_writing_style_corrections.md`) are voice-specific to this researcher and belong in the per-project profile, not the shared pattern reference.

- [ ] **Step 6.1: Read the current profile**

```bash
cat ~/dev/bar-ilan/mikdashim/.academic-helper/profile.md
```

Confirm the file ends with the `## Sources` section and that there is no existing `## Banned Terms` section.

- [ ] **Step 6.2: Append a Banned Terms section to profile.md**

Append (do not replace any existing content) the following block to `~/dev/bar-ilan/mikdashim/.academic-helper/profile.md`:

````markdown

## Banned Terms

Terms the researcher does not use. Section-writer's Skill 2 (Style Fingerprint Compliance) must rewrite any paragraph containing them.

```json
{
  "bannedTerms": [
    { "term": "הכתוב מעיד כי",   "replacements": ["נאמר כי", "הכתוב מציין", "<book> מציג"] },
    { "term": "משרטטים",          "replacements": ["מציגים", "מתארים", "מציעים"] },
    { "term": "עת ",              "replacements": ["כאשר ", "בעת ש", "בשעה ש"] },
    { "term": "הפולחן הקריבני",   "replacements": ["הקרבת הקרבנות", "עבודת הקרבנות"] },
    { "term": "ואני רואה בכך",    "replacements": [], "note": "spontaneous first-person interpretation — remove unless explicitly requested" },
    { "term": "מבחינת",           "replacements": [], "note": "never as a paragraph opener — restate as substantive claim" }
  ]
}
```
````

- [ ] **Step 6.3: Verify the JSON parses**

```bash
python3 -c "import json,re,sys; t=open('/Users/yotamfromm/dev/bar-ilan/mikdashim/.academic-helper/profile.md').read(); m=re.search(r'## Banned Terms.*?```json\s*(\{.*?\})\s*```', t, re.S); assert m, 'banned terms block not found'; json.loads(m.group(1)); print('OK: bannedTerms JSON valid')"
```

Expected: `OK: bannedTerms JSON valid`.

- [ ] **Step 6.4: Commit (in mikdashim repo)**

Switch to the mikdashim project and commit there. From the plugin-dev shell:

```bash
git -C ~/dev/bar-ilan/mikdashim add .academic-helper/profile.md .academic-writer/feedback/
git -C ~/dev/bar-ilan/mikdashim commit -m "profile: add bannedTerms; log mikdash-ezra-nehemia feedback"
```

(If mikdashim is not a git repo, skip the commit step.)

---

## Task 7: Make section-writer Skill 2 honour profile.bannedTerms

**Files:**
- Modify: `src/agents/section-writer.md`
- Test: `tests/test_section_writer_banned_terms.py` (NEW)

- [ ] **Step 7.1: Write the failing structural test**

```python
# tests/test_section_writer_banned_terms.py
from pathlib import Path

SW = Path("src/agents/section-writer.md")

def test_section_writer_loads_banned_terms():
    text = SW.read_text(encoding="utf-8")
    assert "bannedTerms" in text

def test_section_writer_skill_2_rewrites_banned_terms():
    text = SW.read_text(encoding="utf-8")
    # The check must live in Skill 2 (Style Fingerprint Compliance) and reference replacement
    assert "Skill 2" in text
    assert "replacement" in text.lower()
```

- [ ] **Step 7.2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_section_writer_banned_terms.py -v
```

Expected: FAIL.

- [ ] **Step 7.3: Add the bannedTerms check to Skill 2**

Find the "Skill 2: STYLE FINGERPRINT COMPLIANCE" section in `src/agents/section-writer.md`. After its existing scoring logic, append:

````markdown
**Banned-terms sweep (per-project override).** If `.academic-helper/profile.md` contains a `bannedTerms` JSON block, parse it and scan the paragraph for every entry. For each match:

1. If the entry has a non-empty `replacements` array, rewrite the match using the most context-appropriate replacement (favour the first replacement unless it produces awkward Hebrew with the surrounding sentence).
2. If `replacements` is empty, the term is a hard ban — remove the sentence (or rewrite to omit the term entirely).
3. Log the rewrite in the paragraph's audit trail (`section_N_p_M_banned_terms`).

This sweep is mandatory before Skill 3. The pattern reference (`anti-ai-patterns-${language}.md`) covers universal AI tells; `bannedTerms` covers researcher-specific voice. Both must pass.
````

- [ ] **Step 7.4: Run the test to verify it passes**

```bash
python3 -m pytest tests/test_section_writer_banned_terms.py -v
```

Expected: PASS.

- [ ] **Step 7.5: Commit**

```bash
git add src/agents/section-writer.md tests/test_section_writer_banned_terms.py
git commit -m "feat(section-writer): honour profile.bannedTerms in Skill 2"
```

---

## Task 8: Build, structural test, and verify the bundle

**Files:**
- Run: `npm run build`
- Run: `python3 tests/test_plugin_structure.py`
- Run: `python3 -m pytest tests/ -v`

- [ ] **Step 8.1: Build the plugin**

```bash
cd "/Users/yotamfromm/dev/Academic Helper" && npm run build
```

Expected: build completes; `plugins/academic-writer/agents/deep-reader.md`, `architect.md`, `auditor.md`, `section-writer.md`, and `skills/write/SKILL.md` are all updated to match `src/`.

- [ ] **Step 8.2: Run plugin structural tests**

```bash
python3 tests/test_plugin_structure.py
```

Expected: PASS.

- [ ] **Step 8.3: Run the new regression suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all 5 new test files PASS (test_anti_ai_pattern_coverage, test_deep_reader_prompt, test_architect_prompt, test_auditor_prompt, test_write_skill_precondition, test_section_writer_banned_terms — 6 files total).

- [ ] **Step 8.4: Verify src/ ↔ plugins/ parity for the edited files**

```bash
for f in agents/deep-reader.md agents/architect.md agents/auditor.md agents/section-writer.md skills/write/SKILL.md skills/write/references/anti-ai-patterns-hebrew.md; do
  diff -q "src/$f" "plugins/academic-writer/$f" || { echo "DRIFT: $f"; exit 1; }
done && echo "OK: src/ and plugins/ in sync"
```

Expected: `OK: src/ and plugins/ in sync`.

- [ ] **Step 8.5: Commit**

```bash
git add plugins/ src/hooks/dist/
git commit -m "build: rebuild plugin with mikdashim-failure fixes"
```

---

## Task 9: Smoke-test against the mikdashim article

**Files:**
- Read: `~/dev/bar-ilan/mikdashim/articles/mikdash-ezra-nehemia.md`
- Run: regenerate via `/academic-writer:edit` in mikdashim shell

This task is **manual** — it requires running Claude Code interactively in the mikdashim project. Document the procedure here so the researcher (or a fresh session) can repeat it.

- [ ] **Step 9.1: Confirm the existing-article guard fires**

In a new Claude Code session at `cd ~/dev/bar-ilan/mikdashim`, type:

```
/academic-writer:write
```

When asked for the subject, use the same one as the existing article (e.g., "מקדש בתקופה הפרסית בעזרא ונחמיה"). Expected output:

> "An article already exists at articles/mikdash-ezra-nehemia.md.
> Switching to edit mode — running /academic-writer:edit instead of overwriting.
> If you intended to start over, delete articles/mikdash-ezra-nehemia.md first."

Confirm the pipeline did NOT proceed to deep-reader / architect / drafting. The fix from Task 5 is working.

- [ ] **Step 9.2: Run the edit pipeline against the existing article**

```
/academic-writer:edit articles/mikdash-ezra-nehemia.md
```

Ask the edit skill to apply Sections F, G, H of the pattern reference. Expected: the auditor flags any residual unsourced claim, Section F filler, or Section H padding still present in the article.

- [ ] **Step 9.3: Confirm none of the 8 failure modes recur**

Open `~/dev/bar-ilan/mikdashim/articles/mikdash-ezra-nehemia.md` and grep:

```bash
cd ~/dev/bar-ilan/mikdashim
grep -n "מבחינת" articles/mikdash-ezra-nehemia.md && echo "FAIL: F2 recurred" || echo "OK: F2 clear"
grep -n "טכניקה מוכרת" articles/mikdash-ezra-nehemia.md && echo "FAIL: F3 recurred" || echo "OK: F3 clear"
grep -n "ניתן ללמוד כי המתחם נתפס" articles/mikdash-ezra-nehemia.md && echo "FAIL: F4 recurred" || echo "OK: F4 clear"
grep -n "מסכמת את המערך" articles/mikdash-ezra-nehemia.md && echo "FAIL: F6 recurred" || echo "OK: F6 clear"
grep -n "הראוי לבחינה מדוקדקת" articles/mikdash-ezra-nehemia.md && echo "FAIL: F7 recurred" || echo "OK: F7 clear"
head -2 articles/mikdash-ezra-nehemia.md | grep -q "במאמר זה" && echo "OK: F1 clear" || echo "FAIL: F1 — article does not open with במאמר זה"
```

All six lines should print `OK`. If any prints `FAIL`, the corresponding gate did not fire — investigate which task's enforcement is broken before declaring done.

- [ ] **Step 9.4: Regenerate DOCX**

```bash
cd ~/dev/bar-ilan/mikdashim
# Use the plugin's generate-docx.py; path is in the plugin cache
python3 ~/.claude/plugins/cache/academic-writer/academic-writer/0.2.16/scripts/generate-docx.py \
  --input /tmp/aw-article-data.json \
  --output articles/mikdash-ezra-nehemia.docx
```

(The article-data JSON must be reconstructed from the markdown — mirror the existing one in `/tmp/aw-article-data.json` from the prior session, or use whatever the edit skill emits.)

- [ ] **Step 9.5: Final acceptance — commit in mikdashim**

```bash
git -C ~/dev/bar-ilan/mikdashim add articles/mikdash-ezra-nehemia.md articles/mikdash-ezra-nehemia.docx
git -C ~/dev/bar-ilan/mikdashim commit -m "fix: rewrite under fixed pipeline (anti-AI Sections F/G/H, banned terms)"
```

---

## Self-Review

**Spec coverage:** Failures F1–F10 are mapped to tasks (F1, F2 → Task 1 verification; F3 → Task 4; F4–F7 → Task 1 verification of pre-landed Section F/H; F8 → Tasks 2–3; F9 → Task 5; F10 → Tasks 6–7). Build/test/smoke covered by Tasks 8–9.

**Placeholder scan:** No "TBD"/"TODO"/"add error handling" entries. Every code/Markdown step contains the actual content. The only manual step is 9.1–9.5 which is interactive smoke testing — explicitly described as manual.

**Type consistency:** `chapter_coverage` schema (Task 2) is referenced verbatim in the architect's coverage check (Task 3). `bannedTerms` field name (Task 6 profile) matches the section-writer reference (Task 7). `[NEEDS REVIEW: source for "..."]` tag (Task 4) matches the pattern reference's existing convention.

**Order rationale:** Tasks 1–7 each commit independently; Task 8 is the build gate; Task 9 is the production smoke test in the user's project. Tasks 2 and 3 are coupled (architect verifies deep-reader's output) and must land in that order. Tasks 6 and 7 are coupled (profile field + agent that reads it) and must land in that order.
