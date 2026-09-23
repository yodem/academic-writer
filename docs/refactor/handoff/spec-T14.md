# Executor spec — T14 (academic-writer refactor)

Work in this git worktree of the academic-writer plugin. Read `CLAUDE.md` first, then the design
`docs/superpowers/specs/2026-09-23-academic-writer-refactor-design.md` only as needed.

## Rules
- Modify ONLY paths matching these (shell-style globs; `*` spans directories):
- plugins/academic-writer/*
- src/agents/architect.md
- src/cli/*
- src/schemas/author-intent.schema.json
- src/schemas/outline.schema.json
- src/scripts/gate.py
- src/skills/ideate/*
- src/skills/ideate/SKILL.md
- src/skills/write/*
- src/skills/write/SKILL.md
- src/thresholds.json
- tests/test_architect_prompt.py
- tests/test_gate_*.py
- tests/test_gate_outline_v2.py
- tests/test_plugin_structure.py

## Acceptance (all must exit 0)
- `python3 -m pytest -q tests/test_gate_outline_v2.py`
- `python3 -m pytest -q tests`
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


## Task 14: /write W0–W2 — author intent, schema outline, co-author gates

Depends on Task 13.

Depends on Task 11.

**Files:**
- Create: `src/schemas/author-intent.schema.json`
- Create: `src/schemas/outline.schema.json`
- Modify: `src/agents/architect.md`
- Modify: `src/scripts/gate.py`
- Test: `tests/test_gate_outline_v2.py`
- Modify: `src/skills/write/SKILL.md`
- Modify: `src/skills/ideate/SKILL.md`

**Interfaces:**
- Consumes: `evidence.json` (Task 11) and `research-brief.md` from /ideate when present.
- Produces:
  - `author-intent.json`: `{thesis (author's words, verbatim), coreTextSourceId, moves: [string], mustUse: [passageId]}`.
  - `outline.json`: `{thesis, thesisSha256, sections: [{id, title, claim, approved: bool, units: [{id, dependsOn: [id], paragraphs: [{move, evidenceIds: [passageId], bridgeTo: string}]}]}]}`. The architect writes this file directly, validated against the schema.
  - `gate.py outline-v2 --outline <f> --intent <f> --evidence <f>` exits 1 when:
    - any `evidenceIds` fails to resolve;
    - `thesisSha256 != sha256(intent.thesis)`;
    - any `mustUse` passage is unplaced;
    - any section has `approved: false`;
    - there is a cycle in `dependsOn`.

- [ ] **Step 1: Write the failing test.**

```python
# tests/test_gate_outline_v2.py
import json, hashlib, subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).parent.parent
def _files(tmp_path, *, approved=True, must=("p1",), ev_ids=("p1",), thesis="טענה"):
    intent = {"thesis": "טענה", "coreTextSourceId": "s1", "moves": [], "mustUse": list(must)}
    outline = {"thesis": thesis, "thesisSha256": hashlib.sha256(thesis.encode()).hexdigest(),
               "sections": [{"id": "S1", "title": "", "claim": "", "approved": approved,
                             "units": [{"id": "U1", "dependsOn": [], "paragraphs": [{"move": "", "evidenceIds": list(ev_ids), "bridgeTo": ""}]}]}]}
    evidence = {"sources": [{"id": "s1"}], "passages": [{"id": "p1", "sourceId": "s1"}]}
    for n, o in (("i", intent), ("o", outline), ("e", evidence)): (tmp_path/f"{n}.json").write_text(json.dumps(o, ensure_ascii=False))
    return [sys.executable, ROOT/"src/scripts/gate.py", "outline-v2", "--outline", tmp_path/"o.json", "--intent", tmp_path/"i.json", "--evidence", tmp_path/"e.json"]
def test_passes_when_consistent(tmp_path): assert subprocess.run(_files(tmp_path)).returncode == 0
def test_fails_unapproved(tmp_path): assert subprocess.run(_files(tmp_path, approved=False)).returncode == 1
def test_fails_thesis_drift(tmp_path): assert subprocess.run(_files(tmp_path, thesis="טענה אחרת")).returncode == 1
def test_fails_unresolved_evidence(tmp_path): assert subprocess.run(_files(tmp_path, ev_ids=("p9",))).returncode == 1
```

- [ ] **Step 2: Run it and confirm it fails.** Run: `python3 -m pytest -q tests/test_gate_outline_v2.py`
- [ ] **Step 3: Implement.**
  - The `outline-v2` gate.
  - The architect agent rewrite: it takes the intent plus the evidence path, never proposes a replacement thesis (it may add at most 2 labelled alternatives), writes `outline.json`, and uses `omitClaudeMd`.
  - `write/SKILL.md` W0–W2:
    - W0 captures the intent in the author's words (AskUserQuestion plus free text) and seeds it from `research-brief.md`;
    - W1 runs `aw evidence build` in the background;
    - W2 runs the architect dialogue, then shows each section's claim for approval (sets `approved`), then runs the gate.
  - `/ideate` writes `research-brief.md` in a form W0 reads (`## Thesis Direction` → `thesis`).
- [ ] **Step 3b: Jev point `outline.support`.** For each section claim, `aw decide outline.support` (a CLI wrapper over `decide`, fallback = the architect's own support note) is logged, and the label is the author's approval. It is advisory only: it never blocks the gate.
- [ ] **Step 4: Verify.** Run: `python3 -m pytest -q tests`
- [ ] **Step 5: Commit** with the message `feat(write): author-intent, schema outline with paragraph moves, co-author approval gate`.


## Lead addenda (binding)
- `aw evidence build` and `.academic-helper/evidence.json` exist (src/cli/src/evidence.ts; schema src/schemas/evidence.schema.json) — read them; outline evidenceIds must resolve against `passages[].id`.
- `decide()` exists (src/cli/src/decide.ts). For `outline.support`, add a thin `aw decide <point> --question … --options a,b --context-file <f> --fallback <answer> --run <id>` case in main.ts that calls `decide()` and prints JSON; keep it generic (T15 reuses it).
- `--data-dir`/`--project-dir` are required on aw. Tests stub model calls; no network. No `rm` of setup outputs.
- write/SKILL.md must stay <= 500 lines (tests/test_frontmatter_keys.py enforces it); put detail in `src/skills/write/references/`.
- Finish with ALL of: `npm run test:cli`, `npm run typecheck:cli`, `npm run build` (report and continue if its MCP npm step lacks network), `python3 -m pytest -q tests`.

## Worktree housekeeping (lead)
- `.ale-setup-done`, `node_modules`, `src/hooks/node_modules`, `src/cli/node_modules` are ALE setup outputs: never delete, move or `git add` them. Do not run `rm`/cleanup commands on them; the lead removes them before integration.
- Do not revert generated `plugins/` build output by hand; just run `npm run build`.
