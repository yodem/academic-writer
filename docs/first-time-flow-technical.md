# Academic Writer — First-Time Flow (Technical Reference)

Machine-readable specification of the first-time user flow. For AI agents, plugin developers, and automated testing.

---

## Flow Diagram

```
npx academic-writer-setup       (interactive CLI — runs in terminal, no Claude needed)
    |
    v
[CLI Step 1] Prompt: fieldOfStudy (text input, min 3 chars)
    |
    v
[CLI Step 2] Prompt: targetLanguage (select: Hebrew | English | other)
    |
    v
[CLI Step 3] Prompt: citationStyle (select: inline-parenthetical | chicago | mla | apa)
    |
    v
[CLI Step 4] Auto-detect tools (ck, vectorless, cognetivy)
    |           Prompt: multiselect which to enable
    |           NOTE: mongodb-agent-skills is internal to vectorless, not user-facing
    v
[CLI Output] mkdir past-articles/ .academic-writer/ .cognetivy/
    |          Write .academic-writer/profile.json (starter — no fingerprint yet)
    |          Print: "Now run /academic-writer-init in Claude Code"
    v

/academic-writer-init            (runs in Claude Code — analyzes writing style)
    |
    v
[Step 0] Check existing profile (from CLI) → load or start fresh
    |
    v
[Step 3] User drops 5-10 papers into past-articles/
    |    Read PDFs/DOCX → extract text
    |    Analyze → build styleFingerprint (25 dimensions, 8 categories)
    |    Analyze → build articleStructure (sections, intro/conclusion conventions, paragraph formula)
    |    Present to user → user reviews and corrects
    v
[Step 4] If candlekeep.enabled:
    |        User uploads sources: ck items add <file>
    |        Enrich all: ck items enrich <id> (per item)
    |        Build sources[] array (id, title, type)
    |    Else:
    |        sources = []
    v
[Step 5] Update .academic-writer/profile.json
    |    Adds: styleFingerprint, articleStructure, sources
    |    Preserves: fieldOfStudy, targetLanguage, citationStyle,
    |               outputFormatPreferences, tools (from CLI)
    v
[Confirmation] Print summary → user is ready for /academic-writer

========================================================================

/academic-writer
    |
    v
[Load] Read .academic-writer/profile.json
    |   If missing → STOP, tell user: /academic-writer-init
    |   Extract: styleFingerprint, tools, articleStructure, citationStyle
    |   Print fingerprint summary
    v
[Cognetivy] If tools.cognetivy.enabled:
    |            cognetivy run start → store RUN_ID
    |            All subsequent steps log to RUN_ID
    v

=== PHASE 1: CONVERSATIONAL (human-in-the-loop) ===

[Step 1: Subject]
    |   Ask user: topic, angle, ideas
    |   Ask user: targetLanguage for this article
    |   Log: step_completed/subject_selection
    v
[Step 2: Source Selection]
    |   If candlekeep.enabled:
    |       ck items enrich (all) → ck items list --json
    |   Else:
    |       Use profile.sources[]
    |   Present list → user picks sources
    |   Store: selectedSourceIds[]
    |   Log: step_completed/source_selection
    v
[Step 3: Deep Read]
    |   SPAWN: Agent tool → deep-reader subagent
    |       Input: subject, selectedSourceIds, runId, tools
    |       deep-reader queries:
    |           If vectorless.enabled: POST http://localhost:8000/query (modes: mix, local, global)
    |           If candlekeep.enabled: ck items read "ID:pages"
    |       Output: retrieved passages, evidence map, gaps
    |   WAIT for deep-reader to return
    |   Log: step_completed/deep_read
    v
[Step 4: Thesis Proposal]
    |   SPAWN: Agent tool → architect subagent
    |       Input: subject, deep read results, runId, targetLanguage
    |       Output: 2-3 thesis proposals with supporting sources
    |   Present to user → user picks/modifies/writes own
    |   Store: approvedThesis
    |   Log: step_completed/thesis_proposal
    v
[Step 5: Outline]
    |   SPAWN: Agent tool → architect subagent (again)
    |       Input: approvedThesis, deep read results, runId, articleStructure
    |       Output: structured outline (sections with titles, roles, sources, paragraph counts)
    |   Present to user → user reorders/adds/removes
    |   Loop until user approves ("go", "looks good")
    |   Store: approvedOutline
    |   Log: step_completed/outline
    v

=== PHASE 2: AUTONOMOUS (no human input) ===

[Step 6: Ingestion Sync]
    |   If vectorless.enabled AND candlekeep.enabled:
    |       For each selectedSourceId NOT already in vectorless:
    |           content = ck items read "ID:all"
    |           POST http://localhost:8000/documents {name, content, docType}
    |   Log: step_completed/ingestion_sync
    v
[Step 7: Parallel Section Writing]
    |   FOR EACH section in approvedOutline:
    |       SPAWN: Agent tool → section-writer subagent (ALL in parallel)
    |           Input: {
    |               section, sectionIndex, totalSections, thesis,
    |               styleFingerprint (COMPLETE object),
    |               articleStructure, citationStyle, targetLanguage,
    |               linkingWords (from words.txt), runId, tools,
    |               priorSectionTexts, outlineOverview
    |           }
    |
    |   EACH section-writer runs PER PARAGRAPH:
    |       Skill 1: DRAFT
    |           Query vectorless (MANDATORY): POST /query {mode: "mix", query: ...}
    |           Write paragraph using ONLY retrieved context
    |           Log: section_N_p_M_draft
    |       Skill 2: STYLE COMPLIANCE
    |           Score paragraph on 10 fingerprint dimensions
    |           Compare to representativeExcerpts
    |           Fix deviations (target: avg >= 4/5)
    |           Log: section_N_p_M_style_compliance
    |       Skill 3: HEBREW GRAMMAR
    |           Check grammar, spelling, punctuation, academic register
    |           Log: section_N_p_M_hebrew_grammar
    |       Skill 4: ACADEMIC LANGUAGE & LINKING WORDS
    |           Upgrade colloquial vocabulary
    |           Check linking word usage (from words.txt categories)
    |           Ensure 2+ linking words per 3+ sentence paragraph
    |           Log: section_N_p_M_academic_language
    |       Skill 5: LANGUAGE PURITY
    |           Detect ALL embedded foreign-language terms
    |           Replace with target-language equivalent, transliteration, or footnote
    |           Log: section_N_p_M_language_purity
    |       Skill 6: REPETITION CHECK
    |           Check words, phrases, arguments vs. priorSectionTexts + prior paragraphs
    |           Fix with synonyms or restructuring
    |           Log: section_N_p_M_repetition_check
    |       Skill 7: CITATION AUDIT (HARD GATE)
    |           SPAWN: Agent tool → auditor subagent
    |               Input: paragraph, runId, sectionIndex, paragraphIndex, tools
    |               Auditor verifies EVERY citation:
    |                   If vectorless.enabled: POST /query {mode: "bypass"} for exact match
    |                   If candlekeep.enabled: ck items read "ID:page-page"
    |               Output: PASS or REJECT (with reason)
    |           If REJECT:
    |               Rewrite paragraph → re-run skills 1-7 (max 3 attempts)
    |               If still failing after 3 → flag for researcher review
    |           Log: section_N_p_M_citation_audit
    |
    |   WAIT for all section-writers to complete
    |   Collect: allSectionTexts[]
    v
[Step 8: Synthesis]
    |   SPAWN: Agent tool → synthesizer subagent
    |       Input: allSectionTexts, thesis, styleFingerprint (COMPLETE),
    |              articleStructure, linkingWords, runId, tools
    |
    |   Phase A — Synthesis Review (node: synthesize):
    |       Check introduction structure (opens with "במאמר זה", has roadmap)
    |       Check conclusion structure (opens with "לסיכום", recaps, widens)
    |       Argument coherence across sections
    |       Logical flow and transitions
    |       Full-article fingerprint compliance (all dimensions)
    |       Academic language + linking words (full article)
    |       RTL punctuation (Hebrew)
    |       Redundancies and gaps
    |       Language purity (final sweep)
    |       SURGICAL EDITS ONLY — never rewrite full paragraphs
    |       NEVER change or remove citations
    |
    |   Phase B — Repetition Check (node: synthesize_repetition_check):
    |       Cross-section argument repetition
    |       Cross-section phrase repetition (5+ words)
    |       Opening sentence pattern repetition
    |       Transition phrase reuse (max 2x per article)
    |       Evidence reuse (same source for same purpose)
    |
    |   Output: revised article + revision notes
    v
[Step 9: DOCX Output]
    |   Read profile.outputFormatPreferences (or defaults):
    |       Font: David (Hebrew) / Times New Roman (English)
    |       Body: 11pt, Heading: 13pt, Title: 16pt
    |       Line spacing: 1.5, Margins: 1", Alignment: justify
    |       RTL: true (Hebrew) / false (English)
    |   Generate .docx via python-docx:
    |       Title (bold, centered) → thesis (italic, centered) → sections → page numbers
    |   Save to ~/Desktop/<subject>.docx
    |   Log: step_completed/docx_output
    |   Log: run_completed
    |   Print quality report to user
    v
[DONE]
```

---

## Data Flow

```
profile.json ──────────────────────────────────────────────┐
    |                                                       |
    ├── styleFingerprint ─→ section-writer (per paragraph)  |
    |                    ─→ synthesizer (full article)       |
    ├── articleStructure ─→ architect (outline)              |
    |                    ─→ section-writer (intro/conclusion)|
    |                    ─→ synthesizer (structure check)    |
    ├── citationStyle ───→ section-writer, auditor          |
    ├── targetLanguage ──→ ALL agents                       |
    ├── tools ───────────→ ALL agents (skip disabled tools) |
    └── sources[] ───────→ source selection (Step 2)        |
                                                            |
words.txt (linking words) ─→ section-writer (Skill 4)      |
                           ─→ synthesizer (language check)  |
                                                            |
Candlekeep (ck CLI) ───────→ deep-reader, section-writer,  |
                              auditor, source selection     |
                                                            |
Vectorless (localhost:8000) ─→ deep-reader, section-writer, |
                               auditor (bypass mode)        |
                                                            |
Cognetivy (cognetivy CLI) ──→ ALL steps log events ────────┘
```

---

## Agent Spawn Map

```
/academic-writer (main skill)
    |
    ├── Agent tool → deep-reader          (1 instance, sequential)
    ├── Agent tool → architect            (2 calls: thesis, then outline)
    ├── Agent tool → section-writer x N   (N instances, ALL PARALLEL)
    |       |
    |       └── Agent tool → auditor      (1 per paragraph, sequential within section)
    |
    └── Agent tool → synthesizer          (1 instance, after all sections complete)
```

**Parallelism rules:**
- Section-writers: ALL spawn in a single response (parallel)
- Auditors: One per paragraph within each section-writer (sequential)
- Everything else: Sequential (each waits for previous to complete)

---

## Profile Schema (profile.json)

```
{
  fieldOfStudy: string,
  targetLanguage: "Hebrew" | "English" | string,
  citationStyle: "inline-parenthetical" | "chicago" | "mla" | "apa",
  outputFormatPreferences: {
    font: string,
    bodySize: number,
    titleSize: number,
    headingSize: number,
    lineSpacing: number,
    marginInches: number,
    alignment: "justify",
    rtl: boolean
  },
  styleFingerprint: {
    sentenceLevel: { averageLength, structureVariety, commonOpeners, passiveVoice, passiveVoiceExamples },
    vocabularyAndRegister: { complexity, registerLevel, fieldJargon, hebrewConventions },
    paragraphStructure: { pattern, averageLength, argumentProgression, evidenceIntroduction, evidenceAnalysis },
    toneAndVoice: { descriptors[], authorStance, commonHedges[], commonAssertions[], engagementWithScholars },
    transitions: { preferred: { addition[], contrast[], causation[], exemplification[], conclusion[] }, sectionBridging },
    citations: { density, footnotesPerParagraph, integrationStyle, quoteLengthPreference },
    rhetoricalPatterns: { common[], openingMoves, closingMoves },
    representativeExcerpts: string[]   // 5 VERBATIM passages from past articles
  },
  articleStructure: {
    typicalSections: string[],
    introduction: { openingPattern, elements[], elementOrder, includesRoadmap, typicalLength },
    conclusion: { openingPattern, elements[], elementOrder, typicalLength, closingPattern },
    paragraphParts: { typicalFormula, topicSentence, evidencePresentation, analysisType, closingMove },
    sectionTransitions: { pattern, usesTransitionalParagraphs, usesExplicitSignposting }
  },
  tools: {
    candlekeep: { enabled: boolean, version?: string },
    "agentic-search-vectorless": { enabled: boolean, path?: string },
    "mongodb-agent-skills": { enabled: false },   // internal to vectorless, not user-facing
    cognetivy: { enabled: boolean, version?: string }
  },
  sources: [{ id: string, title: string, type: string }],
  createdAt: ISO-8601,
  updatedAt: ISO-8601
}
```

---

## Error States & Recovery

| State | Cause | Recovery |
|-------|-------|----------|
| No profile | Never ran setup | Run `npx academic-writer-setup` then `/academic-writer-init` |
| Empty past-articles/ | No papers provided | Add 5-10 PDFs/DOCX, re-run init |
| Candlekeep not authenticated | CLI installed but not logged in | `ck auth logout && ck auth login` |
| Vectorless repo missing | Not cloned | Clone to `../Agentic-Search-Vectorless/` |
| Cognetivy not initialized | CLI installed but no workspace | `timeout 5 cognetivy init --workspace-only` in project dir |
| Citation audit fails 3x | Source doesn't contain claimed info | Paragraph flagged for researcher review |
| Style fingerprint is flat/legacy | Old init format | Re-run `/academic-writer-init` |

---

## Skill & Agent File Locations

```
.claude/
├── agents/
|   ├── deep-reader.md        # tools: Bash, Read, Grep, Glob
|   ├── architect.md          # tools: Bash, Read, Grep, Glob
|   ├── section-writer.md     # tools: Bash, Read, Grep, Glob, Agent
|   ├── auditor.md            # tools: Bash, Read, Grep, Glob
|   └── synthesizer.md        # tools: Bash, Read, Grep, Glob
└── skills/
    ├── academic-writer/SKILL.md
    ├── academic-writer-init/SKILL.md
    ├── academic-writer-edit/SKILL.md
    ├── academic-writer-edit-section/SKILL.md
    ├── academic-writer-research/SKILL.md
    ├── academic-writer-health/SKILL.md
    ├── academic-writer-help/SKILL.md
    ├── academic-writer-update-field/SKILL.md
    └── academic-writer-update-tools/SKILL.md
```

All agents use YAML frontmatter (`name`, `description`, `tools`, `model: opus`).
All skills use YAML frontmatter (`name`, `description`, `user-invocable: true`).
Skills invoke agents via explicit `Agent tool` language — not prose-style references.
