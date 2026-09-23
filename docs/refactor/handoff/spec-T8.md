# Executor spec — T8 (academic-writer refactor)

Work in this git worktree of the academic-writer plugin. Read `CLAUDE.md` first, then the design
`docs/superpowers/specs/2026-09-23-academic-writer-refactor-design.md` only as needed.

## Rules
- Modify ONLY paths matching these (shell-style globs; `*` spans directories):
- CLAUDE.md
- evals/proofread-recall/*
- features.json
- plugins/academic-writer/*
- src/agents/*.md
- src/agents/copyeditor.md
- src/agents/editor.md
- src/agents/proofreader.md
- src/cli/*
- src/cli/src/prompts/proofread-find.md
- src/cli/src/prompts/proofread-memo.md
- src/cli/src/prompts/proofread-verify.md
- src/cli/src/proofread.ts
- src/cli/tests/proofread.test.ts
- src/schemas/style-words.schema.json
- src/scripts/chunk-article.py
- src/scripts/gate.py
- src/scripts/jev-risk-shadow.py
- src/scripts/must-catch.py
- src/skills/proofread/*
- src/skills/proofread/SKILL.md
- src/thresholds.json
- src/workflows/*
- src/workflows/proofread.js
- tests/e2e/*
- tests/e2e/proofread-recall.mjs
- tests/fixtures/*
- tests/test_aw_binary_runs.py
- tests/test_eval_harness_paths.py
- tests/test_frontmatter_keys.py
- tests/test_jev_risk_shadow.py
- tests/test_must_catch.py
- tests/test_plugin_structure.py
- tests/test_proofread_*.py
- tests/test_schema_drift.py
- tests/test_venue_agnostic.py

## Acceptance (all must exit 0)
- `npm run test:cli`
- `python3 -m pytest -q tests`
- `npm run build`
- `test ! -f src/workflows/proofread.js`
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


## Task 8: Proofread on `aw` — find, verify, memo, apply; retire the workflow

Depends on Task 2. Depends on Task 4.

Depends on Task 5. Depends on Task 6. Depends on Task 7.

**Files:**
- Create: `src/cli/src/proofread.ts`
- Create: `src/cli/src/prompts/proofread-find.md`
- Create: `src/cli/src/prompts/proofread-verify.md`
- Create: `src/cli/src/prompts/proofread-memo.md`
- Create: `src/cli/tests/proofread.test.ts`
- Modify: `src/skills/proofread/SKILL.md`
- Delete: `src/workflows/proofread.js`
- Delete: `src/agents/proofreader.md`
- Delete: `src/agents/copyeditor.md`
- Delete: `src/agents/editor.md`
- Delete: `src/scripts/jev-risk-shadow.py`
- Modify: `tests/test_jev_risk_shadow.py`
- Modify: `src/thresholds.json`
- Modify: `tests/test_plugin_structure.py`

**Interfaces:**
- Consumes: `callGemini` (Task 5), `judge` (Task 6), and `must-catch.py`, `apply-changes.py` and `chunk-article.py --numbered` (Task 7).
- Produces: `aw proofread <article.md> --run <id> [--venue slug] [--only mechanical|language|editorial] --out <dir>`. It writes `<dir>/changes.json`, `<dir>/proofed.md`, `<dir>/report.md` and `<dir>/memo.md`, and prints a JSON summary of at most 1 KB to stdout.
- **Stage order** (spec §4.4):
  1. prepare;
  2. must-catch (always applied);
  3. find: one Gemini call per chunk with line-numbered text; returns `{changes:[{id,line,before,after,class,meaningRisk}]}`;
  4. verify: one batched `judge` call per chunk, only for non-`mustCatch` changes whose `meaningRisk` is applicable (`low`, plus `medium` for class `wrong_word`); the wrong-word class is explicitly in scope;
  5. memo: one call;
  6. apply.
- **Concurrency** comes from `routeFor`. The budget is charged per call.
- **Jev points** (via `decide`, Task 6):
  - `proofread.verify`: per change, with `fallback` = the batched `judge` verdict for that change;
  - `proofread.triage`: per finder candidate, fallback = keep;
  - `style.filler`: per capped style-word hit, fallback = flag.

  All start in `shadow`. A test asserts that with the mode `cascade` and a confident stub, the verify call for that change is skipped.
- **Absorb `src/scripts/jev-risk-shadow.py`** (commit `3d46c9b`). It is an opt-in Jev meaning-risk scorer with `flagScore` 1.5, fitted on 177 Hebrew edits against LLM labels. Its question and threshold become a tenth point, `proofread.risk`, in `decide()`. Its existing `.academic-helper/jev-shadow.jsonl` rows are imported once into the ledger as prior shadow evidence, marked `labelSource: "llm"`: they measure agreement with the LLM, not accuracy, so they do not count toward the 100-label bar. The script and its `proofread.jevShadow` threshold block are removed once `decide()` covers them, and `tests/test_jev_risk_shadow.py` is ported to a `decide` test.

- [ ] **Step 1: Write the failing test** with stub transports: a 3-chunk article, a finder that returns one change per chunk, and a judge that refutes chunk 2's change.

```ts
// src/cli/tests/proofread.test.ts
import { test } from 'node:test'; import assert from 'node:assert/strict';
import { runProofread, __stubs } from '../src/proofread.js';
test('one find + one verify call per chunk; refute downgrades, never drops; must-catch never sent to verify', async () => {
  const calls: string[] = [];
  __stubs({ find: async (c) => { calls.push('find'); return [{ id: `f${c.index}`, line: c.startLine, before: 'x', after: 'y', class: 'typo', meaningRisk: 'low' }]; },
            verify: async (ch) => { calls.push('verify'); return ch.map(c => ({ id: c.id, verdict: c.id === 'f1' ? 'refute' : 'uphold' })); },
            mustCatch: async () => [{ id: 'm1', mustCatch: true, class: 'names_terms', before: 'a', after: 'b', line: 1 }] });
  const r = await runProofread({ chunks: 3, runId: 't' });
  assert.equal(calls.filter(c => c === 'find').length, 3);
  assert.equal(calls.filter(c => c === 'verify').length, 3);
  assert.equal(r.changes.find(c => c.id === 'f1')?.status, 'refuted');
  assert.ok(r.changes.find(c => c.id === 'm1'));
});
```

- [ ] **Step 2: Run it and confirm it fails.** Run: `npm run test:cli`
- [ ] **Step 3: Write the prompts.** Keep them short: role, input format, output contract, and 3 Hebrew examples each drawn from the fixture classes. Voice context for register findings comes from `${dataDir}/voice/rules.md` when present.
- [ ] **Step 4: Implement `proofread.ts`.** Then rewrite `src/skills/proofread/SKILL.md` (≤ 200 lines):
  - frontmatter `context: fork`, and `model`/`effort` per Task 1 `FORK_MODEL`;
  - steps: docx→md (existing script), `aw proofread`, `build-tracked-docx.py`, show the summary.

  Delete the workflow and the three agents, and update `tests/test_plugin_structure.py` for the removed files.
- [ ] **Step 5: Run the recall eval.** Run: `python3 evals/graders/applied_recall.py <out>/proofed.md evals/proofread-recall/fixture/expected.json` after `plugins/academic-writer/bin/aw proofread evals/proofread-recall/fixture/article.md --run eval --out /tmp/aw-eval` (needs a Gemini key; a real run).
- [ ] **Step 6: Verify.** Run: `npm run test:cli`, then `python3 -m pytest -q tests`, then `npm run build`.
- [ ] **Step 7: Commit** with the message `feat(proofread): aw pipeline, deterministic-first, batched cross-family verify; remove workflow`.


## Lead addenda (binding)
- Use the existing CLI modules: `callGemini` (responseSchema), `judge()` (src/cli/src/judge.ts), `decide()` (src/cli/src/decide.ts), `appendLedger`, `routeFor`, `Budget`/`budgetFor('proofread')`. Do not write new clients. Register `aw proofread` as ONE new case in main.ts.
- `aw` takes `--data-dir` and `--project-dir` (required); the plugin root is derived from the binary path (see `pluginRoot()` in pi.ts). Deterministic steps call the Python scripts under `<pluginRoot>/scripts/` via child_process.
- The rewritten `src/skills/proofread/SKILL.md` uses `context: fork` + a pinned `model`, and its body must state plainly that running `aw proofread` is the skill's purpose (a forked subagent refused an unexplained bundled binary in T1).
- Tests stub every model call (no network in your sandbox). The live recall eval (`evals/graders/applied_recall.py` over `evals/proofread-recall/fixture/`) is run by the LEAD after you finish; make `aw proofread` runnable end-to-end so it can be.
- Removing agents/workflow: update every test, CLAUDE.md agents table and features.json entry that references them (grep for the names).
- Finish with ALL of: `npm run test:cli`, `npm run typecheck:cli`, `npm run typecheck`, `npm run build`, `python3 -m pytest -q tests`.

## Worktree housekeeping (lead)
- `.ale-setup-done`, `node_modules`, `src/hooks/node_modules`, `src/cli/node_modules` are ALE setup outputs: never delete, move or `git add` them. Do not run `rm`/cleanup commands on them; the lead removes them before integration.
- Do not revert generated `plugins/` build output by hand; just run `npm run build`.

## FOLLOW-UP (lead review) — finish these, keep everything else you did
12 legacy tests fail because they pin the removed workflow/agents. The allowlist now includes them. Port each to the NEW architecture (do not delete coverage):
- `tests/test_schema_drift.py`: the canonical `src/skills/proofread/references/changes-schema.json` must be the single source. If `src/cli/src/proofread.ts`/prompts embed a copy of the schema, keep the drift test pointed at that copy; if they import the canonical file, replace the drift test with one asserting there is NO inline copy (grep) and that the canonical file parses.
- `tests/test_venue_agnostic.py`: the editorial memo now comes from `src/cli/src/prompts/proofread-memo.md` (or wherever you put it) — assert it always loads the global `editorial-checks.md`, treats a venue profile as optional/additive, and keeps language work out of scope.
- `tests/test_eval_harness_paths.py`: update agent-prompt name resolution for the removed agents (point to the new prompt files).
- `tests/test_no_private_refs.py` failing inside your sandbox is a known sandbox artifact (git index is read-only there) — ignore it.
Run ALL acceptance commands again and paste the final lines.

## FOLLOW-UP 2 (lead ran the LIVE recall eval on the adversarial fixture — real Gemini)
Measured: names_terms 1.00, style_words 0.63, typo 0.23 (targets 0.98 / 0.98 / 0.85); cost ~12k in / 1.8k out Gemini tokens, 0 Claude. Root causes found in `changes.json` — fix ALL, TDD, stubbed tests only:
1. **hspell flag swallows the LLM fix.** 7/13 typos (ההיתיחסות, במישפחה, המיסמכים, הפילוסופייה, הפרשינים, ובעיקבות, להתפתחוט) were must-catch hspell hits with `after: null` (comment-only), and the finder's correction for the SAME span was dropped. Rule: a must-catch item with `after === null` is a *candidate*, not a decision. Merge: if any finder change covers the same span with a non-null `after`, keep the finder's `after` (status `must-catch+finder`, applied, mustCatch true); otherwise keep the flag. Also pass hspell candidates into the find prompt ("these tokens are not in the Hebrew dictionary; propose the correct spelling for each, or return none if the word is a legitimate name/term").
2. **Overlap drops must-catch.** 2 names_terms (רש׳י→רש״י, אבן עזרה→אבן עזרא) got `skipReason: overlap` and were not applied. When a must-catch change (non-null after) overlaps a finder change, the must-catch change wins; the finder change is discarded as `superseded-by-must-catch`.
3. **Wrong-word class.** The find prompt must explicitly target real-word errors in context (examples: לארוס→להרוס, להתפשר אם→עם, הטעון→הטיעון) — include 3–5 such Hebrew examples in `proofread-find.md`, and require every change to carry the class `wrong_word|typo|...`.
4. Add a unit test for each of 1–3 with stubbed model outputs reproducing the eval's shapes.
Acceptance unchanged (all CLI + pytest). Lead re-runs the live eval after.
5. **Capped words have no replacement.** `src/schemas/style-words.schema.json` capped items allow only `{word,maxPer,max}`, and `must-catch.py` emits `after: None` for over-cap uses. Add an optional `replacement: string|null` to capped items (schema + must-catch), used for occurrences beyond the cap. Test: `כמו כן` twice in one paragraph with replacement `נוסף על כך` → the second becomes `נוסף על כך`, the first is untouched.
