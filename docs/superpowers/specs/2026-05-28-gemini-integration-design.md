# Gemini Integration for academic-writer — Design Spec

**Date:** 2026-05-28
**Author:** brainstorming session (Yotam + Claude)
**Status:** approved design, pending implementation plan

## Motivation

Today the academic-writer plugin runs every reader-facing prose phase (drafting, the 6 in-pipeline quality checks, synthesis, edits, calibration samples) on Claude. The researcher wants Gemini to do the prose generation while Claude retains orchestration and the citation audit. Goals:

1. Replace Claude as the prose author for sections, synthesis, edits, and calibration samples.
2. Keep Claude as the orchestrator (`/write`, dispatch), reasoning author (architect), and factual gatekeeper (citation auditor).
3. Self-contained: everything ships inside `plugins/academic-writer/`. No peer plugins. Anyone installing academic-writer gets full Gemini integration in one install.
4. Reusable on the user's PC: the bundled MCP server is globally registered, so the user's other personal plugins can also call its tools.
5. Default-safe for Hebrew: gate Gemini cutover behind a per-language calibration step, given the existing Hebrew anti-AI tuning was authored against Claude's failure modes.

## Architecture overview

```
/write skill (Claude orchestrator)
  └── architect (Claude — outline + evidence ownership)
  └── section-writer per section (Claude, thin)
        Skill 1-7  → MCP: gemini_write_section  (Gemini draft + 6 self-checks)
        Skill 8    → spawn auditor subagent      (Claude — citation gate, unchanged)
  └── synthesizer  → MCP: gemini_synthesize     (Gemini)
  └── voice-calibrator → MCP: gemini_calibrate_sample  (Gemini, for side-by-side)

/edit, /edit-section
  └── prose rewrites → MCP: gemini_edit          (Gemini)
```

The MCP server (`gemini-api`) is declared inside academic-writer's plugin manifest with `${CLAUDE_PLUGIN_ROOT}` substitution. Claude Code starts it automatically when the plugin is enabled. Subagents inherit access to its tools.

## Phase ownership

| Phase | Runtime | Why |
|---|---|---|
| /write orchestration, profile load, dispatch | Claude | Plan-level reasoning, file IO, agent dispatch — no prose |
| architect (outline, evidence ownership) | Claude | Reasoning + structure, not prose |
| section-writer Skills 1-7 | **Gemini** | Drafting + style/anti-AI/linking-words/repetition rewrites — all prose-shaping. One Gemini call per **section** returns all paragraphs already draft + self-reviewed. |
| section-writer Skill 8 (citation audit) | Claude | Sources-lookup + string-match against sources.json + Candlekeep pages. Pure factual gate; no stylistic preference. |
| synthesizer (cross-section polish) | Gemini | Editing prose Gemini wrote |
| voice-calibrator sample paragraph | Gemini | The paragraph evaluated against the voice profile must be the model that will produce real prose |
| /edit, /edit-section | Gemini | Prose rewrites |
| Hebrew (or other language) calibration gate | Claude + Gemini side-by-side | One-time per language, user-approved |

### Why Skills 2-7 move into Gemini (not Claude)

Today's section-writer runs Skills 1-7 as sequential rewrite passes inside one Claude context that has been pre-loaded with the calibration bundle (voice + style fingerprint + linking words + anti-ai-patterns-{lang}.md). If Gemini drafts and Claude rewrites under those same instructions, Claude's stylistic instincts dominate the final prose — defeating the purpose of routing to Gemini.

Moving Skills 2-7 into Gemini's self-review prompt keeps a single voice across the section, halves the per-paragraph LLM cost, and aligns with the user's intent. The trade-off is that the Hebrew anti-AI rules were authored against Claude's failure modes; Gemini may pass the rule set but exhibit different failure modes not yet documented. The per-language calibration gate (below) catches this before any real article ships.

### Why Skill 8 stays on Claude

The auditor checks every citation against `sources.json` and Candlekeep page content — pure lookup + string-match. Its judgments do not depend on prose taste. Keeping it on Claude preserves the existing auditor subagent contract and the persistent behavioral contract in section-writer ("Auditor VERDICT: PASS received" is the non-negotiable gate).

## MCP tool surface

Server: `plugins/academic-writer/mcp/gemini-server/` (Node + TS, esbuild bundle).
Declared in `manifests/academic-writer.json` under `mcpServers > gemini-api`.

### Tools

| Tool | Caller | Input | Output |
|---|---|---|---|
| `gemini_write_section` | section-writer | `{section_brief, sources[], evidence_ownership, banned_terms, target_language, prior_sections_summary, citation_style}` | `{paragraphs: [{text, citations[], self_review_scores}]}` |
| `gemini_synthesize` | synthesizer | `{full_draft, target_language}` | `{revised_draft, change_log}` |
| `gemini_edit` | /edit, /edit-section | `{existing_text, edit_instruction, target_language}` | `{revised_text}` |
| `gemini_calibrate_sample` | voice-calibrator | `{topic_brief, target_language}` | `{paragraph}` |
| `gemini_raw` | other plugins / escape hatch | `{system, prompt, model?, thinking_budget?, temperature?, max_output_tokens?}` | `{text, finish_reason, usage}` |

### Calibration bundle (server-cached)

The server loads the following from `${CLAUDE_PROJECT_DIR}` on the first tool call after server startup and holds them in process memory until the server restarts (server lifetime ≈ Claude Code session lifetime, since the MCP server is spawned by Claude Code when the plugin is enabled):

- `AUTHOR_VOICE.md`
- styleFingerprint JSON block extracted from `.academic-helper/profile.md`
- `plugins/academic-writer/words.md`
- `plugins/academic-writer/skills/write/references/anti-ai-patterns-{target_language}.md` (lowercased; falls back to Hebrew per existing convention)
- `plugins/academic-writer/skills/write/references/style-fingerprint-rubric.md`

Total estimated size: ~13K tokens. Shipped as the system-prompt prefix on every Gemini call.

Gemini caching: this bundle is below the 32K minimum required for **explicit** caching on Gemini 2.5 Pro. The implementation relies on **implicit** caching (75% discount on hits, no minimum, automatic when the same prefix is reused within ~5 minutes) — typical for a writing session that drafts 20-30 paragraphs in 30-90 minutes. The spec notes explicit caching as a future upgrade path once `gemini_raw` users push bundles past 32K.

### Per-call payload (caller-supplied)

Sources used for the paragraph, evidence ownership, banned terms, and section brief are passed inline per call (not cached) because they change per section/paragraph.

### Model defaults

Overridable in `.academic-helper/profile.md > gemini.models`:

| Tool | Default model | Default thinking_budget |
|---|---|---|
| `write_section` | `gemini-2.5-pro` | 8192 |
| `synthesize` | `gemini-2.5-flash` | 2048 |
| `edit` | `gemini-2.5-pro` | 4096 |
| `calibrate_sample` | `gemini-2.5-flash` | 2048 |
| `raw` | `gemini-2.5-pro` | dynamic (-1) |

The server handles the API split internally: `thinkingBudget` (integer) for Gemini 2.5; `thinkingLevel` (categorical: minimal/low/medium/high) for Gemini 3. Callers pass a unified `thinking_budget` integer; the server translates to the right field per model.

Temperature defaults to 1.0 (Gemini's calibrated value). The spec does not lower it — verified evidence that lowering temperature degrades Gemini 2.5 function calling accuracy.

### Self-review prompt (gemini_write_section)

System prompt is composed of:
1. Calibration bundle (cached)
2. Per-call: section brief, evidence-ownership, banned terms, prior-sections summary
3. Instructions block: "For each paragraph: draft, then self-review against the 6 in-pipeline dimensions (style fingerprint compliance, Hebrew grammar, academic language + linking words, language purity, anti-AI, repetition), rewrite below-threshold paragraphs, return final cleaned paragraph with self-review scores."

Tier 1 of Skill 6 (the Python typography fixer at `scripts/detect-ai-typography.py`) remains a deterministic post-processing step run inside section-writer after Gemini returns — it removes em-dashes, straight quotes, directional marks. Gemini cannot reliably guarantee these absent.

## Auth and onboarding

- Primary: `GOOGLE_API_KEY` environment variable. The MCP server reads it from its spawned environment (substituted from the shell env via the manifest).
- Fallback: `.academic-helper/secrets.json` (gitignored, project-scoped) — checked if env var is empty.
- `/academic-writer:setup` walks the user through API key creation and tests it via a one-shot `gemini_raw` ping.

If neither source provides a key:
- The MCP server starts but every tool returns a structured error (`code: "no_credentials"`).
- `/write` warns once at start: "No Gemini key configured. Running on Claude. Run `/academic-writer:setup` to enable Gemini." Then proceeds in Claude-only fallback mode.

## Fallback behavior

### No key
Plugin runs Claude-only (today's behavior). User warned once per session.

### Mid-article transient failure
- Tool calls retry 3× with exponential backoff (defaults in `thresholds.json`).
- After exhausting retries, the calling subagent surfaces a session-level prompt **once**: "Gemini failed mid-write. Continue this article on Claude, or abort and retry later?"
- The chosen mode persists for the rest of the session.
- Drafts written under Claude fallback are marked in `.academic-helper/session-log.json` so the user can see which paragraphs were drafted by which model.

### Language not approved (Hebrew calibration gate)
If `target_language` is not in `profile.md > gemini.approvedLanguages`:
- `/write` invokes voice-calibrator with `--compare-models {target_language}`.
- Calibrator generates one Claude paragraph + one Gemini paragraph from the same brief and source excerpts.
- User reads side-by-side, answers: approve Gemini for this language? (y/n).
- On approval, `gemini.approvedLanguages` is appended in `profile.md`; `/write` proceeds with Gemini.
- On rejection, `/write` falls back to Claude for this language for the session.

The voice-calibrator agent already exists (Haiku, runs at sessions 3 and 7 of voice subsystem). It is extended with the `--compare-models` mode; existing calibration behavior is preserved.

## File touches

### New
```
plugins/academic-writer/mcp/gemini-server/
├── src/
│   ├── index.ts                       # MCP server entry, tool registry
│   ├── tools/
│   │   ├── write_section.ts
│   │   ├── synthesize.ts
│   │   ├── edit.ts
│   │   ├── calibrate_sample.ts
│   │   └── raw.ts
│   ├── bundle.ts                      # calibration bundle loader + in-memory cache
│   ├── gemini-client.ts               # Gemini SDK wrapper, 2.5/3 thinking API split
│   ├── prompts/
│   │   ├── write-section.md           # self-review system prompt template
│   │   ├── synthesize.md
│   │   └── edit.md
│   └── errors.ts                      # structured error codes for fallback
├── package.json
└── tsconfig.json

scripts/build-mcp.sh                   # esbuild bundle → mcp/gemini-server/dist/
```

### Modified
- `manifests/academic-writer.json` — add `mcpServers.gemini-api`
- `src/agents/section-writer.md` — Skill 1 becomes single `gemini_write_section` call returning all paragraphs of the section already cleaned; Skills 2-7 removed from this agent (now Gemini-internal); Skill 8 (auditor dispatch) unchanged; explicit fallback branch for MCP errors → today's in-context Skills 1-7
- `src/agents/synthesizer.md` — call `gemini_synthesize`; fallback branch
- `src/agents/voice-calibrator.md` — add `--compare-models` mode; persist `gemini.approvedLanguages`
- `src/skills/write/SKILL.md` — pre-flight calibration gate; mid-run failure prompt
- `src/skills/edit/SKILL.md`, `src/skills/edit-section/SKILL.md` — route through `gemini_edit`; fallback
- `src/skills/setup/SKILL.md` — `GOOGLE_API_KEY` onboarding + ping test
- `src/thresholds.json` — add `gemini.maxOutputTokens.*`, `gemini.retry.{maxAttempts, backoffMs}`, default `gemini.models.*` map
- `package.json` — esbuild script for MCP server
- `scripts/build-plugins.sh` — also build MCP server dist
- `tests/test_plugin_structure.py` — assert manifest declares MCP server; assert `dist/index.js` exists post-build; assert tool count

## Testing

- **Unit:** mocked Gemini API responses. Verify bundle assembly, thinking-API split per model family, error mapping to structured codes, retry logic.
- **Integration:** fixture project with synthetic `.academic-helper/`. Spin up MCP server, call each tool with realistic inputs, assert output shape and citation pass-through.
- **Calibration gate:** synthetic profile with `approvedLanguages: []` → first `/write` triggers the gate; `[]` after rejection → Claude fallback; `["he"]` → Gemini path.
- **Fallback paths:** simulate API error mid-section, assert session-level prompt fires once and persists; simulate missing `GOOGLE_API_KEY` and assert Claude-only mode + single warning.

## Risks and open questions

- **Hebrew quality unverified.** The 178-line Hebrew anti-AI ref was authored against Claude. The calibration gate is the empirical check; if the side-by-side fails repeatedly, the spec for Skills 2-7 in Gemini may need a language-specific addendum to the self-review prompt (a Gemini-failure-modes reference parallel to the Claude one).
- **Implicit caching unverified for actual session timing.** A writing session that drafts paragraphs more than ~5 minutes apart may miss cache hits and pay full Pro rates. Implementation should log cache hit rates from Gemini's `usage.cached_content_token_count` field and surface a session summary so the user can see real cost.
- **MCP server crash recovery.** If the server crashes mid-write, all subsequent tool calls fail. Plan: on N consecutive failures, the calling subagent escalates to session-level prompt rather than retrying forever.
- **Synthesizer over-rewriting.** If Gemini's synthesis pass rewrites paragraphs that the auditor already approved citations on, citation integrity may break. Constraint: synthesizer prompt must explicitly forbid rewriting citation text, footnote markers, or any string inside citation parentheses.

## Out of scope (future work)

- Embeddings via Gemini (no current RAG need in the plugin).
- Streaming tool responses (single-response MCP is simpler; can add later).
- Gemini 3 GA migration (preview models documented as upgrade path; no code change needed beyond model defaults).
- Cost dashboards beyond per-session summary.
- Promoting Skills 2-7 from "Gemini self-review" to "Gemini drafts + Claude reviews" for a language where empirical evidence shows Gemini self-review is unreliable.

## Success criteria

1. Installing academic-writer plus setting `GOOGLE_API_KEY` enables Gemini for all reader-facing prose with no further configuration.
2. First `/write` in a new language triggers the calibration gate.
3. On Gemini outage, the user is asked once whether to continue on Claude; the chosen mode persists for the session and is logged.
4. No `.academic-helper/` writes happen outside the existing setup/init/write skills (preserves the project's "no global pollution" rule).
5. Existing tests pass + new tests cover MCP declaration, fallback paths, and calibration gate.
