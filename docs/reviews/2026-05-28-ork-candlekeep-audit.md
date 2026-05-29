# Full-Codebase Audit — academic-writer plugin (2026-05-28)

**Method:** `ork:audit-full` (multi-dimension) + CandleKeep-grounded standards audit. Authoritative
yardstick: *Claude Code: Official Docs*, *The Complete Guide to Building Skills for Claude*,
*Inside Claude Code: The Architecture*, *Anthropic Engineering Playbook* (page citations inline).

**Scope:** manifest/build, skills (16), agents (10), hooks (5 handlers), bundled Gemini MCP server,
prompts, pipeline architecture, TS hook code.

---

## CRITICAL / HIGH

### [HIGH] Bundled Gemini MCP server is never registered in the distributed plugin
- **Where:** `scripts/build-plugins.sh:117-133` generates `plugin.json` from a **hardcoded jq literal**
  that emits only `name, version, description, author, homepage, repository, license, keywords`.
  It never reads `mcpServers` from `manifests/academic-writer.json`. `scripts/build-mcp.sh` builds the
  server binary but registers it in **no** manifest, and **no `.mcp.json`** is emitted at the plugin root.
- **Evidence:** `plugins/academic-writer/.claude-plugin/plugin.json` contains **0** `mcpServers` entries
  and no `.mcp.json` exists under `plugins/academic-writer/`. The source manifest
  (`manifests/academic-writer.json:24-34`) *does* declare `gemini-api`. Corroboration: no
  `mcp__gemini-api__*` tool was present in this audit session.
- **Standard:** "Plugins define MCP servers in `.mcp.json` at the plugin root or inline in `plugin.json`."
  — *Claude Code: Official Docs*, p.85. There is no third registration path; the server is unreachable.
- **Impact:** 3 agents (`section-writer`, `synthesizer`, `voice-calibrator`) and 3 skills
  (`edit`, `edit-section`, `setup`) reference `mcp__gemini-api__*` tools that have no registration path.
  `section-writer`/`synthesizer` fall back to a **self-contained in-context pipeline** on MCP error, so
  **sections are still written** — but the entire Gemini acceleration feature (commits
  `fa337a9`, `af01cc9`, `d7d99db`) is **dead-on-arrival and silent** in shipped form. HIGH, not CRITICAL,
  because the fallback degrades gracefully (verified: `section-writer.md:282-375` fallback needs no Gemini tool).
- **Note — overturns the ork:audit-full claim.** The forked `ork:audit-full` pass reported
  "Manifest registers the server with the correct env passthrough." That read the **source** manifest and
  never traced the build generator. The CandleKeep-grounded full audit caught what the forked audit missed.
- **Fix direction (not applied — audit only):** have the generator merge `mcpServers` (and any extra
  manifest keys) from `manifests/*.json`, OR emit a `.mcp.json` at the plugin root during Phase 4.

---

## MEDIUM

### [MED] Source manifest is misleading — generator ignores most of it
- `manifests/academic-writer.json` declares `mcpServers`, `skills:"all"`, `agents:"all"`, `hooks:"all"`,
  and keywords `docx`/`hebrew`. The generator (`build-plugins.sh:117-133`) reads only `name/version/description`
  and **hardcodes** author/homepage/repository/license/keywords. So editing the manifest's author, keywords,
  or mcpServers has **no effect** on the build. `skills/agents/hooks:"all"` are not valid `plugin.json`
  schema fields either (*Official Docs*, p.114 lists the recognized set) — they're vestigial build-config the
  script never consumes (it copies dirs unconditionally).
- **Impact:** maintainability trap — the manifest looks authoritative but is partly inert.

### [MED] `voice-migrate.sh` is not profile-scoped (ran in this non-consumer repo)
- **Where:** `src/hooks/hooks.json:25-33` runs `skills/voice/voice-migrate.sh` directly at `SessionStart`,
  bypassing `run-hook.mjs`. Its only guard is the `.voice` dir (`voice-migrate.sh:13,22`); it does **not**
  check `.academic-helper/`.
- **Evidence:** it emitted `voice-migrate: already migrated …; skipping` at the start of *this* session —
  the plugin dev repo, which has **no `.academic-helper/`**. The `run-hook.mjs`-gated hooks correctly no-op
  (guard at `run-hook.mjs:54-59`, exit 0 silent — matches *Official Docs* p.60).
- **Standard / project convention:** CLAUDE.md: "every hook must silently skip in projects without
  `.academic-helper/profile.md`." voice-migrate violates this.
- **Impact:** SessionStart side-effects + visible output in unrelated projects that merely have the plugin enabled.

---

## LOW / INFO

### [LOW/verify] Skills use `allowedTools` (camelCase), spec field is `allowed-tools`
- All 16 SKILL.md use `allowedTools:`. *Official Docs* p.106 canonical field is `allowed-tools`. Skills load
  fine in this session, so it doesn't break discovery; open question is whether the **auto-approve** semantics
  are honored from the camelCase key. The build script tolerates both forms when generating `commands/*.md`
  (`build-plugins.sh:144`), and the generated command files emit kebab-case `allowed-tools:` (line 148), so the
  generated commands are spec-correct. Project CLAUDE.md mandates `allowedTools` — if CC ignores camelCase in
  SKILL.md, every skill silently loses its pre-approval list. **Verify against installed behavior.**

### [LOW] `voice` skill has empty `metadata:` and bare-string `allowedTools`
- `src/skills/voice/SKILL.md`: `metadata:` is empty (no `author`/`version`), violating the project convention
  ("Add `metadata: {author, version}` to skills"). `allowedTools` is a bare comma string (valid per spec, but
  inconsistent with the array form used by the other 15 skills).

### [INFO] Headroom guard is dead code for 4 of 5 Gemini tools (from ork:audit-full)
- `mcp/gemini-server/src/gemini-client.ts:240` — the `maxOutputTokens` headroom guard added in `d7d99db` runs
  only when the caller passes `max_output_tokens`. The 4 template tools never do; the real fix for the live
  failure was the default-budget reduction. Re-raising a thinking budget later would re-trigger the original
  bug with no guard. (Moot in distribution until the MCP server is actually registered — see HIGH above.)

### [INFO] Verbatim-fidelity tools run at temperature 1.0 (from ork:audit-full)
- `gemini-client.ts:237` defaults temp 1.0; `edit`/`synthesize` are spec'd to preserve citations/quotes
  verbatim. Downstream Claude auditor is still the hard gate, so impact is bounded.

---

## Verified clean (from ork:audit-full)
- No API-key/payload leakage in errors; stdout JSON-RPC hygiene; secrets via env → gitignored
  `secrets.json` fallback; strict TS, zero `any`, `tsc --noEmit` clean; zod in/out validation on every tool;
  `dist/`+`node_modules/` gitignored; build fails loudly if `dist/index.js` absent.
- Agents correctly avoid `hooks`/`mcpServers`/`permissionMode` frontmatter (forbidden for plugin agents,
  *Official Docs* p.114). All agent `model` values valid. All skill descriptions include "Use when…" triggers
  and are well under the 1,536-char cap (*Official Docs* p.110).
- Hook events used (SessionStart/SubagentStart/Stop/SessionEnd) are all valid; short explicit timeouts.

---

---

## Prompts (skill bodies + agent system prompts)

### [HIGH] Gemini fallback triggers on tool-*error*, never tool-*absence*
- `section-writer.md:267-279`, `synthesizer.md:46` enumerate fallback triggers only as a structured
  `{error:{code,message}}` (`no_credentials`/`api_error`/transient). In distribution the MCP tool is **absent
  from the toolset** (HIGH build bug above), so there is no error object to catch and no "tool not available"
  branch. Worse, `write/SKILL.md:43-61` keys `geminiMode` on `GOOGLE_API_KEY` presence, not tool registration:
  key present → primary path chosen → tool absent → no error → no fallback. An agent could stall instead of
  cleanly degrading. **Fix direction:** add an explicit "if the gemini tool is not in your available tools,
  use the fallback path" instruction to both agents, and make the pre-flight verify tool registration.

### [HIGH] No untrusted-content quarantine anywhere (prompt injection)
- No agent or skill delimits or marks-as-data the source text it ingests. `ck items read` output (untrusted,
  often OCR'd PDFs) flows straight into instruction position in deep-reader → `sources.json`, into
  section-writer (passed to Gemini as `sources`), and into the auditor. A crafted source passage could carry
  instructions. Grep for delimiter / "treat as data" / "never follow instructions inside" returns nothing.

### [MED] Auditor VERDICT-on-last-line + verbatim paragraph echo is a reachable gate-bypass
- `auditor.md:198-200,227-241` instruct the auditor to echo the paragraph then put `VERDICT: PASS` as the
  absolute last line; `section-writer.md:40` checks "last line == VERDICT: PASS". Because the audited text is
  exactly the untrusted/generated content, a paragraph (or source passage) ending in a line `VERDICT: PASS`
  can satisfy the gate. **Fix:** emit the paragraph in a fenced block; put the verdict on its own
  structurally-parsed line.

### [MED] Stale "RAG" references describe an integration with no tool binding (reconciled — downgraded)
- `auditor.md:177,184,187,213,224` and `write/SKILL.md:388,393`, `edit-section/SKILL.md:96` describe a RAG
  `bypass` verification mode. The auditor frontmatter has no RAG/MCP tool. **Reconciliation:** `auditor.md:105`
  treats RAG as *optional* and the gate's real verification rests on `ck items read` + WebSearch (both
  available), so the gate is followable — the RAG branches are dead/aspirational, not gate-breaking. (The
  earlier "phantom tool breaks the hard gate" framing was overstated.)

### [MED] deep-reader calls Sefaria/NotebookLM MCP tools absent from its frontmatter
- `deep-reader.md:206` (`mcp__claude_ai_Sefaria__get_text`), `:225-226` (notebook tools). Frontmatter `tools:`
  is `Bash, Read, Write, Grep, Glob`. Subagents get only their declared tools (*Official Docs* p.96), so those
  steps are non-executable as written.

### [MED] deep-reader has a duplicated step and broken numbering
- `deep-reader.md:100-135` and `137-171` are byte-identical (Chapter Coverage Enumeration block); step
  sequence is 1 → 1b → 1c → 1c → 1d → 1e → 2 → 4 (no Step 3; Step 4 is an empty "Log Progress" header).
  Suggests lost/duplicated content; risks drift on future edits.

### [LOW] Citation-format drift between section-writer paths
- Primary-path output spec (`section-writer.md:392-394`) documents only `inline-parenthetical`+`chicago`;
  fallback (`:312-320`) adds `mla`/`apa`+biblical format. `citationStyle` allows all four, so an mla/apa
  article on the primary path has no output-format guidance.

### [LOW] `write/SKILL.md` is 597 lines — over the 500-line SKILL.md guideline (*Official Docs* p.106)
- Only file exceeding it; bulk is inline bash + a Step-6 pipeline table that duplicates section-writer's contract.

**Strong point:** citation/hallucination guards ("never infer year/journal/publisher", `[?]` low-confidence
marker, `extractionConfidence`) are consistent across deep-reader → section-writer → auditor — the
best-specified part of the system.

---

## Pipeline & architecture

### [HIGH] Parallel spawn defeats the run-wide Gemini fallback commit → mixed-engine sections
- `write/SKILL.md:354` spawns all section-writers in one parallel response; the `geminiFallback` flag only
  affects agents "spawned after this point" (`:89`, `section-writer.md:277`), so the in-flight batch can't be
  made consistent. On intermittent failure (sections 1–2 on Gemini, section 3 hits `api_error` and
  self-falls-back without asking), one article gets some Gemini-styled and some Claude-styled sections. The
  synthesizer is not designed as a cross-engine style unifier. (Moot while the server is unregistered, but a
  latent design fault for when it's fixed.)

### [HIGH] Edit Modes C/F mutate cited prose without re-auditing
- `edit/SKILL.md:118-159`: Mode C (tone) and Mode F (cut/expand) rewrite existing cited sentences but do not
  spawn the auditor; only Modes A/B/E re-audit. The Critical Rule (`:199`) covers "new claims" but not mutation
  of already-cited sentences. Citation integrity can drift on the edit path.

### [MED] Threshold-key mismatch bounds the hard gate's rewrite cap on an inline literal (CONFIRMED)
- `section-writer.md:242,375` + `write/SKILL.md:398` cite `thresholds.json > audit.maxRewriteAttempts`, which
  **does not exist**; the real key is `rewriteCycles.max` (thresholds.json:16), referenced by no prose file.
  Editing thresholds.json has zero effect on the cap (both default to 3, so behavior is correct by
  coincidence). The `subagent-start` hook reads the *correct* key, so the auditor's injected note and the
  section-writer's enforcement read different sources for the same gate.

### [MED] Parallel non-atomic rewrite of `evidence-ownership.json` can corrupt coordination state
- `section-writer.md:248-263`: every parallel section-writer does a full read-modify-write of the whole file.
  Overlapping writers lose appends (last-writer-wins, acknowledged `:263`) and can clobber `evidenceOwners` /
  `thesisAnchor` — fields actively read for back-reference dedup (`:306`), per-paragraph thesis-drift guard
  (`:142`), and synthesizer evidence consolidation (`synthesizer.md:163`). `claimsRegistry` itself is
  **write-only** (no consumer), so the lost-claims race is harmless; the collateral corruption of the read
  fields is the real risk.

### [MED] "Expand my draft" path skips the architect → `evidence-ownership.json` never created
- `write/SKILL.md:296` (`userDraftAsOutline=true`) skips the architect, the sole writer of
  `evidence-ownership.json` (`architect.md:174-202`). Section-writers then read `{}` and both coordination
  safeties (thesis-drift guard, cross-section dedup) silently no-op.

### [MED] Edit pipeline never reads/refreshes `sources.json`
- Auditor Check D verifies metadata against `.academic-helper/sources.json` (`auditor.md:107-122`). Neither
  edit skill re-runs deep-reader nor reads the registry; if it's stale (deep-reader overwrites it per write,
  `deep-reader.md:94`) or absent, edits get weaker citation verification than the original write.

### [MED] deep-reader `chapter_coverage` is validated by the architect but never persisted
- `architect.md:30` rejects/re-spawns deep-reader on coverage gaps, but `chapter_coverage` is absent from the
  deep-reader Output template and never written to disk, so the completeness safety is largely inert.

### [MED] Inlined gate numbers shadow thresholds.json (CLAUDE.md anti-pattern)
- `220`-word ceiling hardcoded (`section-writer.md:169,308`, `write/SKILL.md:381`) with no threshold key;
  `35/50` anti-AI inlined in `anti-ai-patterns-{hebrew,english}.md` (loaded verbatim into scoring, can diverge
  from `antiAi.passThreshold`); `40/60` inlined in `write/SKILL.md:469` + `scorecard.json:4`.

### [LOW] [NEEDS REVIEW] escape hatch makes the gate soft on the worst-case path
- `section-writer.md:242,375`: after max rewrites, a never-PASSed paragraph reaches output with a
  `[NEEDS REVIEW]` tag — contradicting the contract's "do not move on" (`:40`). Intentional (avoids infinite
  loops) but there's no separate marker distinguishing "low-confidence metadata" from "unverifiable citation".

**Verdict:** serial backbone (deep-reader → architect → section-writer → auditor → synthesizer) is sound and
the citation gate is well-specified; the *parallel* execution model is the consistent weak point (fallback
incoherence + non-atomic shared-state rewrite), and the edit path + threshold-key sourcing are the
citation-integrity liabilities.

---

## TS hook code

### [HIGH] `voice-pull` hook is dead in every real install (path bug)
- `voice-pull.ts:15` resolves the sync script at `join(projectDir, "src", "skills", "voice", "voice-sync.sh")`
  — anchored to the *user's project dir* and using the `src/` source layout. At runtime the script is at
  `${CLAUDE_PLUGIN_ROOT}/skills/voice/voice-sync.sh`. `existsSync` fails → early return. The
  "Pulling latest voice profile…" SessionStart hook never pulls in any installed environment.

### [MED] subagent-start delivers auditor context via `systemMessage`, reads thresholds from wrong path (reconciled)
- `subagent-start.ts:55` uses `systemMessage` (user-facing) rather than the canonical
  `hookSpecificOutput.additionalContext` (*Official Docs* p.61); `HookResult` (`types.ts:25-29`) can't even
  express `additionalContext`. **Reconciliation:** `auditor.md`'s body is self-contained, so the gate still
  has its rules — the injection is supplementary (a one-line threshold summary). Also `:30` reads
  `.academic-helper/thresholds.json`, but thresholds.json ships at the plugin root, so the note is usually
  empty. Net: non-canonical channel + likely-empty note; bounded impact, not a gate break. (Earlier
  "hard-gate context never reaches the subagent" framing was overstated.)

### [MED] session-dashboard advertises command names that don't exist
- `session-dashboard.ts:69,77-80` print `/academic-writer-ideate`, `-learn`, `-health` (hyphenated). Plugin
  skills namespace as `/academic-writer:<skill>` (*Official Docs* p.106; CLAUDE.md command table). `learn` is
  `user-invocable:false`, so it isn't a command at all. First-launch output points researchers at commands
  that won't resolve.

### [LOW/MED] 100ms stdin race can deliver empty input
- `run-hook.mjs:84-89`: if no stdin chunk arrives within 100ms, the runner invokes the hook with `{}`.
  subagent-start then sees no `subagent_type` (no injection); session-end-log loses `session_id`. Prefer
  waiting for `end`/`error` over assuming a 100ms gap means closed stdin.

### [LOW] Box-drawing width math breaks on Hebrew/wide values; voice-sync leaves a `.tmp` on timeout
- `session-dashboard.ts:21-51` `padEnd` counts UTF-16 units, not display columns → RTL values misalign the
  border (cosmetic). `voice-sync.sh:77-87` can orphan `AUTHOR_VOICE.md.tmp` if the 10s SessionStart hook is
  killed mid-pull (non-destructive; live only once voice-pull is fixed).

**Verdict:** defensively written, security-clean, compiles strict (zero `any`), and never crashes the session
(exit-code + try/catch discipline is genuinely good). But `voice-pull` is dead in every real install, the
auditor-context channel is non-canonical, and the dashboard advertises non-existent commands — all
correctness/trust issues despite the solid foundation.

---

## Severity roll-up

| # | Severity | Finding | Anchor |
|---|----------|---------|--------|
| 1 | HIGH | Gemini MCP server never registered in built manifest | build-plugins.sh:117-133 |
| 2 | HIGH | Fallback triggers on tool-error, not tool-absence | section-writer.md:267-279 |
| 3 | HIGH | No untrusted-content quarantine (injection) | all agents |
| 4 | HIGH | Parallel spawn → mixed-engine sections on intermittent Gemini failure | write/SKILL.md:354 |
| 5 | HIGH | Edit Modes C/F mutate cited prose without re-auditing | edit/SKILL.md:118-159 |
| 6 | HIGH | voice-pull hook dead in every real install (path bug) | voice-pull.ts:15 |
| 7 | MED | Source manifest misleading (generator ignores most of it) | build-plugins.sh:117-133 |
| 8 | MED | voice-migrate.sh not profile-scoped | hooks.json:25-33 |
| 9 | MED | Auditor VERDICT-last-line echo = gate-bypass vector | auditor.md:198-241 |
| 10 | MED | Threshold-key mismatch (audit.maxRewriteAttempts ✗) | section-writer.md:242 |
| 11 | MED | Parallel non-atomic evidence-ownership.json rewrite | section-writer.md:248-263 |
| 12 | MED | Draft-expansion path skips architect → no ownership file | write/SKILL.md:296 |
| 13 | MED | Edit pipeline never reads/refreshes sources.json | edit/SKILL.md |
| 14 | MED | Stale RAG references (no tool binding) | auditor.md:177-224 |
| 15 | MED | deep-reader calls Sefaria/NotebookLM tools not in frontmatter | deep-reader.md:206 |
| 16 | MED | Inlined gate numbers shadow thresholds.json | section-writer.md:169 |
| 17 | MED | subagent-start: systemMessage channel + wrong thresholds path | subagent-start.ts:30,55 |
| 18 | MED | Dashboard advertises non-existent command names | session-dashboard.ts:69 |
| 19 | LOW | camelCase allowedTools vs spec allowed-tools (verify) | all SKILL.md |
| 20 | LOW | voice skill empty metadata / bare-string allowedTools | voice/SKILL.md |
| 21 | LOW | Citation-format drift between section-writer paths | section-writer.md:392 |
| 22 | LOW | write/SKILL.md 597 lines > 500-line guideline | write/SKILL.md |
| 23 | LOW | 100ms stdin race; box-width math; tmp-file litter | run-hook.mjs:84 |
| 24 | INFO | Headroom guard dead code for 4/5 Gemini tools | gemini-client.ts:240 |
| 25 | INFO | Verbatim-fidelity tools at temperature 1.0 | gemini-client.ts:237 |

**Headline:** the distributed plugin still *functions* (graceful fallback everywhere), but the entire Gemini
acceleration layer is dead-on-arrival because the build generator drops `mcpServers`, and that single bug
cascades into the fallback-absence, mixed-engine, and orphaned-tool findings. The forked `ork:audit-full`
missed it by reading source not build; the CandleKeep-grounded full audit caught it.
