# Determinism audit & enforcement design — 2026-09-04

**Repo:** `~/dev/learning/Academic Helper` · **Branch:** `main` @ `c94181b`
**Rule source:** CandleKeep `cmtifqy5a2cpun00jzpuztuca` ("Personal · Agent Best Practices"), chapters 7 (`WRK`), 9 (`ACI`), 10 (`TST`), 12 (`VER`), read 2026-09-04. The book is **ahead of** the wiki register at `wiki/projects/ai-agent-best-practices.md` (it carries `WRK-24..29`, `TST-08/09`, `VER-12..19`, several extracted from this plugin's own sessions); the book is treated as authoritative.

**Version stamp (`VER-09`):** this audit reads the working tree at `c94181b`. Every verdict below is stale the moment a later commit touches the cited `file:line`.

**Supersedes in part:** `docs/audits/2026-09-02-agents-vs-best-practices.md`. Three of its findings are no longer true at HEAD — see § 1.

---

## 1. Corrections to the 2026-09-02 audit (`VER-09`)

The prior audit is two days old and three of its load-bearing claims have since been overtaken. Recording the ruled-out branches rather than silently dropping them (`SPC-07`).

| Prior finding | Then | Now at `c94181b` |
|---|---|---|
| #2 — "`find src/workflows` returns nothing; the orchestrator today is `src/skills/write/SKILL.md`, itself a prompt" — rated **HIGH FAIL** on `WRK-13`/`WRK-14` | true on 2026-09-02 | **Closed for the workflow path.** `src/workflows/write-sections.js` (648 ln) and `src/workflows/proofread.js` (493 ln) both exist. `write-sections.js:411-435` runs the rewrite loop with the cap read from `args.thresholds` (`:23`), parses the auditor's post-fence `VERDICT:` line by regex (`:308-318`), and names every exit `PASS`/`NEEDS_REVIEW` (`:634`). That is `WRK-14` done correctly. |
| #1 — "schema conformance asserted to the LLM with nothing downstream" — rated **HIGH FAIL** on `TST-02` | true as stated | **Largely closed.** Every `agent()` call in both workflows passes a `schema:` option — `proofread.js:224, 266, 291, 368, 399`; `write-sections.js:293, 388, 587, 622` — which the workflow runtime enforces at the boundary. That is `ACI-12` ("constrain first, prompt second") already applied. Remains open **only** for the documented prose-fallback paths. |
| #13 — premise that a CandleKeep book was orphaned | corrected in that audit | unchanged |

**A new risk the correction exposes.** `proofread.js:77-79` states the script "cannot Read changes-schema.json off disk … by convention", so `CHANGES_SCHEMA` is an **inline duplicate** of `src/skills/proofread/references/changes-schema.json`. Same for the five schemas in `write-sections.js:160`. Two copies of one contract, free to drift, with nothing asserting they agree. This is a better-targeted version of finding #1 than "write a validator script."

Still open from that audit, re-verified at HEAD: finding #3 (architect Coverage Pre-Check), finding #6 (`features.json` "partial" entries with no issue note), finding #7 (`section-writer.md` fallback duplication), finding #8 (`voice.ruleCoverage` warn == block), finding #10 (stale CHANGELOG).

---

## 2. The finding

The user's stated premise was that the plugin "isn't deterministic enough" and "relies too much on skills." For the generation stage that is **no longer accurate** (§ 1). The real gap is narrower and structural:

> **The enforcement surface and the guard scripts cannot reach each other.**

| Layer | Can exec a script? | Can block? | Reality at `c94181b` |
|---|---|---|---|
| Workflow (`src/workflows/*.js`) | **No** — no fs/exec by design, asserted by `tests/test_write_workflow.py::test_no_filesystem_access` | Yes — owns loops and caps | Owns every cap; cannot run a single guard |
| Hook (`src/hooks/src/lifecycle/*.ts`) | Yes | Yes | **All five return `continue: true`** — `notify-stop.ts:26`, `session-end-log.ts:42`, `session-dashboard.ts:84`, `subagent-start.ts:57`, `voice-pull.ts:29`. Zero enforce anything. |
| Skill (`SKILL.md`) | Yes | **No** — prose a model may skip | Where 10 of 11 Python guards are actually triggered |

Call-site survey of every deterministic script (`grep -rl` over `src/skills`, `src/agents`, `src/workflows`, `src/hooks/src`): all eleven are referenced, none are dead. But only **one** — `apply-changes.py`, from `proofread.js` — is invoked from executable code. The other ten fire because a `SKILL.md` sentence tells a model to run them.

By `WRK-14`'s own test — *"could an agent's judgment change this? If yes, it is not a gate"* — ten of eleven guards are not gates.

Blocking hooks are available and proven on this machine: `~/.claude/hooks/guard-writes.py` is a `PreToolUse` hook exiting `2`, and `PostToolUse`/`Stop` are used by 20 and 28 installed plugin hook registrations respectively. The capability exists; this plugin does not use it.

### Measured cost

`/academic-writer:write`, using the skill's own cited sizing (`write/SKILL.md:361`, 12–16 writer units; N=14, ~3 paragraphs/unit, `rewriteCycles.max`=3):

- clean run (every paragraph passes audit first try) — **≈ 77 LLM invocations**
- pathological (every paragraph exhausts all 3 attempts) — **≈ 329**

`/academic-writer:proofread`, 8,000-word article → 7 chunks:

- **≈ 300 LLM invocations**, dominated not by the bounded find-stages but by the refute-verify fan-out.

### The unbounded term (new — not in the 2026-09-02 audit)

`proofread.js:297` loops `for (const rawChange of list)` and calls `refuteChange` once per change, each spawning up to `refuteVotes`=3 lens agents (`:299-302`). `concurrencyCap`=6 bounds **parallelism only** — it is a batch-slicing window (`:125`, `:140`), not a volume cap. Nothing anywhere bounds `list.length`. A chunk returning 50 findings costs 150 verify calls. The same shape repeats in the mechanical stage at `:354-382`.

`thresholds.json:42-50` claims to hold "Proofread pipeline caps … (WRK-14)". It caps chunk size, pass count, dry rounds, parallelism, and vote count — every dimension except the one that actually drives cost.

### A config comment that contradicts its own code

`thresholds.json:49` — *"refuteMajority of them refuting **drops** it."*
`proofread.js:305` — `verifiedChanges.push({ ...change, applied: false, skipReason: 'refuted', refutedBy })`.

It downgrades. It never drops, exactly as the workflow's own header mandates (`proofread.js:14-18`). The single source of truth is wrong about the gate it configures.

---

## 3. Design

Approach chosen: **a gate dispatcher invoked by a blocking hook**, with the four missing guard scripts as its payload. Rejected: exposing guards as MCP tools — an agent that simply does not call the tool passes, so it fails `WRK-14`'s test and is not a gate.

### 3.1 `src/scripts/gate.py` — one typed entry point

A single dispatcher, `ACI-03` exit codes (`0` pass · `1` gate failed · `2` could not run), `--json` for machine consumption, one narrow typed argument set per subcommand (`ACI-12`).

| Subcommand | Replaces | Check |
|---|---|---|
| `gate argument-graph <outline.json>` | `write/SKILL.md:310-325` — *"This is not a subagent call; it is reasoning directly over the outline JSON already in memory"* | DFS cycle detection over `depends_on`, orphan nodes, empty `evidence` arrays, missing `thesis_link`, topological orderability. Emits violating node ids. |
| `gate coverage <deep-read.json>` | `architect.md:28-41` | Every entry has `status` ∈ {covered, skipped-irrelevant}; chapter numbers form a contiguous `1..max` range; every `evidence_ids` entry resolves in the evidence map. |
| `gate citation-floor <article.md> --sources <sources.json>` | nothing — new, per `VER-18` | Counts citations, classifying secondary vs primary (primary sources stay inline, so a raw count reads healthy at 13 secondary). Exits non-zero below a floor read from `thresholds.json`. |
| `gate changes-schema <changes.json>` | the prose-fallback half of audit finding #1 | `jsonschema` validation against the canonical on-disk `changes-schema.json`. `jsonschema>=4.20` is already in `requirements-dev.txt`. |

**Why `VER-18` earns its own gate:** the per-paragraph citation auditor is a presence check — it verifies that claims which *are* cited are cited correctly. It is structurally blind to a paragraph that cites nothing. The absent-thing check is arithmetic, not judgment.

### 3.2 The gate ledger + `Stop` hook — making a skipped gate detectable

`gate.py` appends each verdict to `.academic-helper/session-state.json` under a `gates` key (the file already exists and is already written by `write/SKILL.md:54`; nothing in `src/hooks/` currently reads it).

New hook `src/hooks/src/lifecycle/gate-enforce.ts`, registered on **`Stop`**:

- reads `session-state.json`; if no run is in flight, `continue: true` (and, per the project's profile-scoping convention, `run-hook.mjs:54` already skips everything when `.academic-helper/` is absent);
- if a run is in flight and a **required gate is missing or failed**, returns `continue: false` with a `systemMessage` naming the gate and the violating ids;
- honours `stop_hook_active` so a gate that cannot be satisfied cannot trap the session in a loop;
- fails **closed** on a genuine gate failure and **open** on its own infrastructure errors (missing script, unreadable ledger) — a gate that breaks the plugin in projects that never opted in is worse than the gap it closes.

This is what makes the design work: skipping the gate call entirely is itself caught, because the ledger records absence. That is `VER-18` applied to the enforcement layer itself.

`types.ts` gains `SubagentStop` to `HookEvent` and `stop_hook_active?: boolean` to `HookInput`.

**Deliberate limitation, stated rather than hidden:** a `Stop` hook gates the *end of the turn*, not the moment of the violation. A model can still skip a guard mid-run; it cannot finish while an artifact fails one. Earlier `PostToolUse` feedback is possible but is out of scope here (§ 4).

### 3.3 Persist the outline

`gate argument-graph` needs the outline on disk; today it lives only in the orchestrating session's context. `write/SKILL.md` Step 5.5 must write `.academic-helper/outline.json` before validating. This is a prerequisite for the gate and independently makes the argument graph auditable after the fact (`VER-09`).

### 3.4 Bound the refute fan-out

New `thresholds.proofread.refuteBudgetPerChunk`. Changes beyond the budget are carried as `applied: false, skipReason: 'refute-budget-exhausted'` — **downgraded, never dropped**, matching the contract `proofread.js:14-18` already commits to. The budget is spent on the highest-`meaningRisk` changes first, so exhausting it degrades gracefully rather than arbitrarily.

### 3.5 Two corrections

- `thresholds.json:49` — "drops it" → "downgrades it to `applied: false`", matching `proofread.js:305`.
- New test asserting the inline `CHANGES_SCHEMA` in `proofread.js` is structurally equal to `src/skills/proofread/references/changes-schema.json`, and the same for `write-sections.js`'s inline schemas — closing the drift risk from § 1.

---

## 4. Out of scope, with reasons

- **Roster pruning.** The prose→Gemini / factual-gate→Claude model split is a validated invariant across three plugins (`concepts/Multi-Agent Writing Pipeline.md`); `WRK-18`'s "conflicting system-prompt objectives" forcing function genuinely applies to writer-vs-auditor. Decision recorded: move the graph, keep the roles.
- **`PostToolUse` per-write gating.** Real, but a second enforcement surface before the first one has proven itself is speculative. Revisit once the `Stop` gate has run on live articles.
- **The 2017 כתיב מלא lookup table** (audit finding #4). The prior audit already reasoned that the lookup half is scriptable and the exception half (proper names, deliberate pre-2017 text, internal consistency) is not. Splitting it is a separate call, not a determinism gap.
- **`section-writer.md`'s ~110-line fallback duplication** (finding #7). Real, still open, but it is a prose-refactor, not an enforcement gap.
- **Guards as MCP tools.** Rejected — see § 3.
- **`Stop`-hook enforcement for `/proofread`.** Deferred deliberately, and this is a real gap, stated rather than hidden: `write/SKILL.md` writes a ledger `run` with `requiredGates`, so the hook enforces the write path; `/proofread` writes none, so a proofread run currently has zero required gates and the hook is a no-op there. The reason is that its one gate, `changes-schema`, is **path-conditional** — on the Workflow path the contract is already enforced by each `agent()` call's `schema:` option, so requiring the gate unconditionally would block legitimate runs that correctly never invoked it. Wiring it properly means setting the ledger run only on the fallback branch, which is worth doing once the write path's enforcement has run on real articles. Until then `/proofread`'s schema check is a documented step in `proofread/SKILL.md`, not a hard gate.

---

## 5. Acceptance criteria

Per `TST-08`, **no gate is trusted until it has been proven able to fail.** Every gate below ships with a mutation test that plants the defect and asserts the non-zero exit:

| Gate | Mutation that must make it fail |
|---|---|
| `argument-graph` | an outline with `A depends_on B`, `B depends_on A` |
| `argument-graph` | a unit with `evidence: []` |
| `coverage` | a `chapter_coverage` array skipping chapter 3 |
| `coverage` | an `evidence_ids` entry with no match in the evidence map |
| `citation-floor` | an article whose secondary-citation count sits one below the floor |
| `changes-schema` | a change object missing `rationale` |
| `gate-enforce` hook | a `session-state.json` with a run in flight and a required gate absent → `continue: false` |
| `gate-enforce` hook | `stop_hook_active: true` → `continue: true`, no loop |
| refute budget | a chunk with `refuteBudgetPerChunk + 1` findings → the surplus carries `skipReason: 'refute-budget-exhausted'` and **is still present in the output** |
| schema drift | mutate the on-disk `changes-schema.json` → the drift test fails |

Per `TST-09`, no gate test may depend on an ambient binary being on `PATH`; environment-dependent branches get a temp-`PATH` stub, never a skip.

The existing suite (346 passing at `c94181b`, `python3 -m pytest -q`) plus `npm run typecheck` must stay green, and the new tests join CI's existing "Gate — deterministic test suite" step.

## 6. As built — deviations from § 3, and verification

Implemented on 2026-09-04 on top of `c94181b`. Every deviation from the design above is listed here rather than silently absorbed.

**Deviations**

1. **The refute budget is cumulative per chunk, not per round.** § 3.4 said "per chunk"; a naive per-round reading would let one chunk spend the full budget again on each of `maxPasses` rounds, i.e. up to 3× the stated cap. `proofread.js` tracks spend in a `mechanicalBudgetSpent` map across residual rounds. This matches `thresholds.json`'s own wording ("how many changes per chunk are sent for refute-verification **at all**").
2. **The inline `CHANGES_SCHEMA` in `proofread.js` had already drifted** from the canonical file — missing `stage` in the change-level `required`, missing `change_id`/`applied`/`skipReason`/`refutedBy`, no `type` enum. It was harmonized to the canonical schema rather than encoding the drift as a permanent carve-out in the drift test. **This introduced a defect that was caught and fixed:** requiring per-change `stage` while only the *editorial* prompt asked the model for it would have failed structured-output validation at runtime in the language and mechanical stages. Both prompts now state it explicitly (`proofread.js:343`, `:466`).
3. **A gate that exits 2 writes `status: "error"` to the ledger**, so an *unrun* gate blocks at `Stop` exactly as a *failed* one does. An unrun gate is not a passed gate.
4. **`coverage`'s input schema is not pinned by any existing file.** It was designed from `architect.md` / `deep-reader.md` prose and documented in `gate.py`'s module docstring. The evidence map reaches the architect in its prompt, not on disk, so `architect.md` now writes it to `/tmp/aw-deep-read.json` before invoking the gate.
5. **`citation-floor` reuses `citation-guard.py`'s `FOOTNOTE_RE`/`PAREN_CITATION_RE`** rather than new regexes, loaded via `importlib` because the filename is hyphenated. A real bug was fixed in passing: consecutive footnote definitions with no blank line between them were being merged, losing footnotes 2–8.

**Verified, by running the commands, not by reading the code**

- Full suite `python3 -m pytest tests/ -q` → **444 passed, 0 failed** (346 at baseline, +98 new).
- `npm run typecheck` → clean. `npm run build` ships `scripts/gate.py` and registers `gate-enforce` alongside `notify-stop` under `Stop`.
- All six CI gates pass locally (version-sync, built-manifest, version-consistency, no-private-refs, mcp-dist, typecheck).
- **End-to-end integration** (each batch had only tested its own half): a cyclic outline → `gate.py` exit 1 reporting `cycle` *and* `ordering` as separate violations → ledger records `status: "fail"` → `Stop` hook returns `continue: false` → outline repaired, gate re-run → `continue: true`.
- Exit 1 and exit 2 are genuinely distinguishable: a change missing `rationale` → 1; malformed JSON → 2.
- Hook fail-open/fail-closed proven separately: missing required gate → blocks; `stop_hook_active` → passes; no `profile.md` → silent pass.

**Pre-existing defect found, not fixed (out of scope, flagged for a decision)**

`tests/test_tracked_docx.py::NoMatchSkipTests::test_skip_leaves_document_byte_comparable_to_omitting_the_change` byte-compares two DOCX files that each embed a wall-clock timestamp, so it fails whenever the two builds straddle a second boundary. It failed once during this work and passed 3/3 in isolation; neither it nor `build-tracked-docx.py` is in this diff. This is a `TST-09` environment-dependent test and it will flake in CI at random.

## 7. Rule mapping

| Change | Rules satisfied |
|---|---|
| `gate.py` dispatcher, typed args, real exit codes | `TST-02`, `ACI-03`, `ACI-12` |
| `Stop` hook enforcement + ledger | `WRK-14`, `VER-18` |
| `argument-graph`, `coverage` gates | `TST-02`, `WRK-20` (a deterministic check is a **tool**, not a reasoning step) |
| `citation-floor` | `VER-18` |
| refute budget | `WRK-14` |
| mutation tests | `TST-08` |
| environment-controlled tests | `TST-09` |
| schema-drift test | `ACI-12` |
| this document, commit-stamped, superseding the prior audit in part | `VER-09`, `SPC-07` |
