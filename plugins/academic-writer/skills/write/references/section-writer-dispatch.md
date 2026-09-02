# Section-Writer Dispatch Detail (Step 6)

> Read this when you reach Step 6 (Parallel Section Writing + Auditing) in SKILL.md — it has the
> full engine-commit procedure and the exact prompt fields each spawned `section-writer` needs.

## Step 6.0: Engine commit (run BEFORE the parallel spawn)

Because all section-writers are spawned in a single parallel response, the engine decision must be **final before the spawn** — once the batch is in flight, `geminiFallback` can no longer be made consistent across writer units. Commit the whole run to one engine here:

1. **Verify Gemini actually works with a live call — do not stop at "the key file has a value."** A key can be present-but-invalid/expired, or the key can resolve while the plugin's `mcp__plugin_academic-writer_gemini-api__*` MCP tools are absent from your toolset (e.g., the server failed to register). A file-presence or field-truthy check reports healthy in both of those broken states, so it is not sufficient on its own.
   - First confirm `mcp__plugin_academic-writer_gemini-api__gemini_write_section` (or any `mcp__plugin_academic-writer_gemini-api__gemini_*` tool) appears in your available tools.
   - Then fire one real, cheap probe call to `mcp__plugin_academic-writer_gemini-api__gemini_calibrate_sample` with trivial input (e.g. a one-line sample) and confirm it returns a normal result rather than a `no_credentials` / `api_error` / transport error. This is the actual live ping — treat it as required, not optional, since it is the only check that catches an invalid or expired key.
2. **If `geminiMode` is `"gemini"` but the tool is unavailable, unregistered, or the live probe call fails/errors** (including `no_credentials` even though the file/env check passed), set `.academic-helper/session-state.json > geminiFallback: true` now — before spawning. The user has already been asked once during the mid-run failure handler / pre-flight, so do not re-ask here; this is a registration/liveness check, not a runtime failure.
3. **Read the committed `geminiFallback` value once**, and pass that SAME value to EVERY section-writer spawned for EVERY writer unit in the parallel batch below.

> **Never mix engines across writer units — decide once, before the parallel spawn, and pass `geminiFallback` uniformly.** Every writer unit across every section must run on the same engine; a half-Gemini/half-Claude article cannot be style-unified by the synthesizer.

## Spawning: one subagent per writer unit

**CRITICAL: Use the Agent tool to spawn one `section-writer` subagent per WRITER UNIT. Call the Agent tool multiple times in a single response — one call per unit — so all writer units write in parallel.**

A section with no `units` array in the approved outline is itself a single writer unit — spawn exactly one subagent for it, same as before. A section WITH a `units` array is NOT itself spawned directly — spawn one subagent per entry in its `units` array instead. The parallel fan-out count for this step is therefore the total number of writer units across the whole outline, which may exceed the number of top-level sections.

## Per-unit prompt fields

For each writer unit in the approved outline, the Agent tool prompt must include:
- `unit`: the writer unit's own spec — its `id`, `claim`, `evidence`, `depends_on`, `thesis_link`, `argument_role`, and target words (from thresholds.json's `writerUnit` fields, e.g. `writerUnit.targetWords`)
- `parentSection`: the parent section's overall brief/thesis-link context (title, `argument_role`, `thesis_link`) — for a section with no `units` array, this can mirror the unit's own info or be omitted as trivial
- `siblingUnitsSummary`: a short summary of sibling units' briefs/claims within the same section, so prose transitions flow naturally between subsections — only relevant/non-empty when the section has multiple units
- `sectionIndex`: the PARENT section's number in the outline
- `totalSections`: total top-level section count
- `unitIndex` / `unitId`: the unit's own id within its parent section (e.g. `"II.1"`)
- `totalUnitsInSection`: how many writer units the parent section contains
- `thesis`: the article thesis
- `articleStructure`: the researcher's structure conventions
- `citationStyle`: from the profile
- `targetLanguage`: from the profile
- `targetWordCount`: the requested article length (so each unit is sized proportionally)
- `tools`: the enabled tools
- `priorSectionTexts`: text of all previously completed sections/units (for repetition awareness)
- `outlineOverview`: full outline titles and roles
- `userDraftParagraphs`: (if `userDraftAsOutline = true`) the user's draft text for this unit — agents expand this rather than writing from scratch
- `geminiFallback`: the value committed in Step 6.0 above (read from `.academic-helper/session-state.json`). Pass the SAME value to every section-writer in this batch — never spawn some units with `true` and others with `false`.

**NOTE:** Do NOT pass `styleFingerprint`, `linkingWords`, `sourcesRegistry`, or `evidenceOwnership` in the prompt — section-writer agents load all four directly from disk to reduce context size:
- Fingerprint from `.academic-helper/profile.md`
- Linking words from `${CLAUDE_PLUGIN_ROOT}/words-{lang}.md`, selected by the article's `targetLanguage` (falls back to `words-hebrew.md` if no language-specific file exists)
- Source registry from `.academic-helper/sources.json` (deep-reader output)
- Evidence ownership map from `.academic-helper/evidence-ownership.json` (architect output)

## Per-paragraph 8-skill pipeline

Each section-writer handles a **per-paragraph 8-skill pipeline** internally — in order: Draft → Style Compliance → Grammar Check (language-specific, dispatched by `targetLanguage`) → Academic Language → Language Purity → Anti-AI → Repetition Check → Citation Audit (logged per paragraph as `section_N_p_M_<skill>`). The authoritative contract for that pipeline — exact skill behavior, the 220-word ceiling, the `thresholds.json`-driven anti-AI gate, and the auditor hard gate (Citation Audit / Skill 8) — lives in the `section-writer` agent definition (`${CLAUDE_PLUGIN_ROOT}/agents/section-writer.md`). Do not duplicate or override it here; the orchestrator only spawns section-writers and waits for their results.
