# Executor spec — T15 (academic-writer refactor)

Work in this git worktree of the academic-writer plugin. Read `CLAUDE.md` first, then the design
`docs/superpowers/specs/2026-09-23-academic-writer-refactor-design.md` only as needed.

## Rules
- Modify ONLY paths matching these (shell-style globs; `*` spans directories):
- manifests/academic-writer.json
- scripts/build-plugins.sh
- src/agents/auditor.md
- src/agents/section-writer.md
- src/agents/synthesizer.md
- src/cli/src/draft.ts
- src/cli/src/edit.ts
- src/cli/src/ocr.ts
- src/cli/src/prompts/write-draft.md
- src/cli/src/prompts/write-synthesize.md
- src/cli/src/synthesize.ts
- src/cli/tests/draft.test.ts
- src/skills/edit-section/SKILL.md
- src/skills/edit/SKILL.md
- src/skills/ocr/SKILL.md
- src/skills/write/SKILL.md
- src/workflows/write-sections.js

## Acceptance (all must exit 0)
- `npm run test:cli`
- `python3 -m pytest -q tests`
- `npm run build`
- `test ! -d plugins/academic-writer/mcp`
- `bash scripts/smoke-built-plugin.sh`

## Global Constraints

- Numbers are never inlined. Every cap, budget, model id and concurrency lives in `src/thresholds.json` (new keys `models`, `budget`).
- Gemini runs on flash only, the latest id. Model ids appear only in `src/thresholds.json > models`.
- **Where the plugin writes.** Plugin runtime writes only inside the project (`CLAUDE_PROJECT_DIR`) and `${CLAUDE_PLUGIN_DATA}`. Nothing else under `$HOME`.
- **API keys.** Keys come only from userConfig `sensitive` values or the environment. The plaintext `.academic-helper/secrets.json` path is removed.
- **Hook guard.** Every hook silently skips a project without `.academic-helper/profile.md`.
- **Strict TypeScript.** No `any`. `npm run typecheck` passes for hooks and the CLI.
- **Failures are named.** A step that exceeds its budget exits `CAP_REACHED` or `ERROR`. A missing verdict is `ERROR`, never `PASS`. Model errors never fall back silently to another model.
- **Frontmatter.** Skills use documented frontmatter keys only: `name`, `description` (with "Use when…"), `allowed-tools`, `user-invocable`, `disable-model-invocation`, `model`, `effort`, `context`, `metadata`. Agents use `name`, `description`, `tools`, `disallowedTools`, `model`, `omitClaudeMd`.
- **Size.** Every SKILL.md is ≤ 500 lines.
- **Tests.** The existing suite stays green: `python3 -m pytest -q tests` (519 passing at the 2026-09-23 baseline, after rebasing onto `3d46c9b`).
- **Release.** Every slice ends with a release: version bump through `scripts/version-sync.py`, `npm run build`, marketplace refresh, and `claude plugin update`.
- **ALE and Codex stay out of the plugin.** The shipped plugin never calls the `ale` CLI or Codex.
- **Pi is isolated.** Pi is called only through `judge()` (Task 6), always with the isolation flags. The plugin stores no OpenRouter key; Pi's own auth owns it.
- **Jev runs only through `decide()`.** Every Jev use goes through `decide()` (Task 6) with a per-point mode in `thresholds.json > jev.points`. Hebrew points start in `shadow`, and moving a point to `cascade` is a release decision (at least 100 labels and the roster bar). Jev never skips the Claude citation auditor.


## Task 15: /write W3–W6 on `aw` — ordered drafting, batched audit, diff synthesis; retire MCP server

Depends on Task 13.

Depends on Task 6. Depends on Task 10. Depends on Task 14.

**Files:**
- Create: `src/cli/src/draft.ts`
- Create: `src/cli/src/synthesize.ts`
- Create: `src/cli/src/edit.ts`
- Create: `src/cli/src/ocr.ts`
- Create: `src/cli/src/prompts/write-draft.md`
- Create: `src/cli/src/prompts/write-synthesize.md`
- Create: `src/cli/tests/draft.test.ts`
- Modify: `src/agents/auditor.md`
- Modify: `src/skills/write/SKILL.md`
- Modify: `src/skills/edit/SKILL.md`
- Modify: `src/skills/edit-section/SKILL.md`
- Modify: `src/skills/ocr/SKILL.md`
- Delete: `src/workflows/write-sections.js`
- Delete: `src/agents/section-writer.md`
- Delete: `src/agents/synthesizer.md`
- Modify: `manifests/academic-writer.json`
- Modify: `scripts/build-plugins.sh`

**Interfaces:**
- Consumes: `outline.json`, `author-intent.json` and `evidence.json` (Tasks 11 and 14), `voiceBundle` (Task 10), `judge` (Task 6), and `callGemini`/`Budget` (Task 5).
- Produces:
  - `aw draft --outline <f> --run <id> [--unit <id>]`:
    - it drafts body units in topological order of `dependsOn`; each call gets the full outline, the final text of its predecessors, its passages from `evidence.json`, and the voice bundle;
    - it drafts `intro` and `conclusion` last, from the body's claim sentences;
    - it writes `drafts/<unit>.md` and runs the code gates;
    - it exits 2 on any gate failure, naming the unit and gate.
  - The draft gates:
    - citation keys ∈ `sources.json`;
    - every quoted span ∈ `evidence.json` passages, verbatim;
    - the `style-words.json` banned/capped rules;
    - word bounds from `thresholds.writerUnit`.
  - `aw synthesize --outline <f> --run <id>` returns paragraph-level `{unitId, paragraphIndex, before, after, reason}` transition edits, applied by code. It never rewrites the whole article.
  - `aw edit` and `aw ocr` are ports of the MCP `edit` and `ocr` tools with the same inputs.
  - The auditor gets one batched call per unit (847c831 shape) with `taggedText` in its schema. It stays the hard gate. With a key, the OpenRouter judge runs the same batch in shadow and the agreement is logged to `events.jsonl`.
  - **Jev points** (via `decide`):
    - `write.audit_prescreen` per paragraph, logged only. The Claude auditor always runs while the gate is active, and a test asserts that `cascade` mode still calls the auditor for this point.
    - `write.voice_check` per paragraph (fallback = the `voice-score` threshold).
    - `synthesize.needs_bridge` per boundary (fallback = the synthesize call decides).
  - The manifest drops `mcpServers.gemini-api`. The build no longer copies `mcp/`, and `plugins/academic-writer/mcp/` is deleted after its source is confirmed moved into `src/cli`.

- [ ] **Step 1: Write the failing test.**

```ts
// src/cli/tests/draft.test.ts
import { test } from 'node:test'; import assert from 'node:assert/strict';
import { draftAll, __stubs } from '../src/draft.js';
test('dependency order, predecessors passed, intro/conclusion last, non-verbatim quote fails the gate', async () => {
  const seen: { unit: string; preds: string[] }[] = [];
  __stubs({ gen: async (u, preds) => { seen.push({ unit: u.id, preds: preds.map(p => p.id) }); return u.id === 'U3' ? 'כתוב ״ציטוט שאינו במקור״' : `טקסט ${u.id}`; },
            evidenceQuotes: ['ציטוט מהמקור'], voice: { exemplars: [], pairs: [], rules: '', styleWords: { banned: [], capped: [], filler: [] } } });
  const outline = { units: [ { id: 'intro', role: 'intro', dependsOn: [] }, { id: 'U1', dependsOn: [] }, { id: 'U2', dependsOn: ['U1'] },
                             { id: 'U3', dependsOn: ['U2'] }, { id: 'conclusion', role: 'conclusion', dependsOn: [] } ] };
  const r = await draftAll(outline, { runId: 't' });
  assert.deepEqual(seen.map(s => s.unit).slice(0, 3), ['U1', 'U2', 'U3']);
  assert.deepEqual(seen.find(s => s.unit === 'U2')?.preds, ['U1']);
  assert.deepEqual(seen.slice(-2).map(s => s.unit).sort(), ['conclusion', 'intro']);
  assert.equal(r.failures[0]?.unit, 'U3'); assert.equal(r.failures[0]?.gate, 'quote-not-in-evidence');
});
```

- [ ] **Step 2: Run it and confirm it fails.** Run: `npm run test:cli`
- [ ] **Step 3: Implement** `draft.ts`, `synthesize.ts`, `edit.ts` and `ocr.ts`, porting from `plugins/academic-writer/mcp/gemini-server/src/tools/*.ts`, and the prompts.
  - **Draft prompt order:** reference first (evidence passages, predecessor text, outline), then voice (exemplars, pairs, rules), then the task, with the output contract last. The prompt is written in the article's language.
- [ ] **Step 4: Rewrite `write/SKILL.md` W3–W6** (the whole skill ≤ 450 lines):
  - `aw draft` runs in the background per layer;
  - the auditor subagent gets one batched call per unit;
  - failed paragraphs go to `aw draft --unit <id>` with the auditor's feedback, up to `rewriteCycles.max`;
  - then `aw synthesize`, then `generate-docx.py`;
  - then it tells the author to comment in Word and run `/academic-writer:revise`.

  Also:
  - Update `edit`, `edit-section` and `ocr` to call `aw`.
  - Delete the workflow, `section-writer.md` and `synthesizer.md`.
  - Remove `mcpServers` from the manifest and `mcp/` from the build.
  - Update `tests/test_plugin_structure.py`, and remove or port `tests/test_mcp_dist*.py` and the `tests/e2e/*gemini*` harnesses to `aw`.
- [ ] **Step 5: Verify.** Run: `npm run test:cli`, then `python3 -m pytest -q tests`, then `npm run build`, then `test ! -d plugins/academic-writer/mcp`.
- [ ] **Step 6: Commit** with the message `feat(write): ordered drafting on aw, batched audit gate, diff synthesis; retire MCP server and workflows`.


## Worktree housekeeping (lead)
- `.ale-setup-done`, `node_modules`, `src/hooks/node_modules`, `src/cli/node_modules` are ALE setup outputs: never delete, move or `git add` them. Do not run `rm`/cleanup commands on them; the lead removes them before integration.
- Do not revert generated `plugins/` build output by hand; just run `npm run build`.
