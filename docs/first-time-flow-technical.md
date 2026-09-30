# First-time flow: technical reference

What happens, in code, between installing the plugin and the first `.docx`. For plugin developers and anyone debugging a first run. The researcher-facing version is [first-time-flow.md](first-time-flow.md). This page describes version 0.14.0 plus the unreleased changes in [CHANGELOG.md](../CHANGELOG.md); the source files named below are authoritative when they disagree with it.

---

## Components

| Piece | Where | Role |
|---|---|---|
| Skills | `src/skills/<name>/SKILL.md` | The conversation. User-invocable skills become `/academic-writer:<name>` commands; `learn`, `present`, `update-field` and `update-tools` are `user-invocable: false` and are reached by plain-language requests. |
| `aw` CLI | `src/cli/src/*.ts`, shipped as `plugins/academic-writer/bin/aw` | Every model call and deterministic step, invoked from Bash. All model steps route to Gemini (`thresholds.json > models`) and need `GOOGLE_API_KEY`. |
| Agents | `src/agents/architect.md`, `src/agents/auditor.md` | `architect` writes the outline; `auditor` is the citation hard gate. No other agents ship. |
| Hooks | `src/hooks/hooks.json`, `src/hooks/src/lifecycle/*.ts` | Profile-scoped: each one is a no-op in a project without `.academic-helper/profile.md`. |
| Scripts | `src/scripts/*.py` | Deterministic gates (`gate.py`), DOCX generation (`generate-docx.py`), proofread helpers, style metrics. |
| Thresholds | `src/thresholds.json` | Every numeric limit and model id. Copied into `.academic-helper/` by setup. |

There is no MCP server, no dynamic workflow runner, and no section-writer, synthesizer or deep-reader agent; 0.14.0 removed them.

---

## Install and session start

```text
/plugin marketplace add yodem/academic-writer
/plugin install academic-writer@yodem
```

On every `SessionStart`, in this order (see `src/hooks/hooks.json`):

1. `lifecycle/session-env` receives `${user_config.google_api_key}` and `${user_config.jev_api_key}` and, **only if `.academic-helper/profile.md` exists**, appends `export GOOGLE_API_KEY=...` (and `JEV_API_KEY`) to Claude Code's session env file. Unset options that arrive as the literal placeholder text are ignored.
2. `lifecycle/session-dashboard` prints the dashboard.
3. `lifecycle/voice-pull` runs `skills/voice/voice-sync.sh pull` (non-fatal on failure).
4. `skills/voice/voice-migrate.sh` migrates legacy voice files.

Other hooks: `SubagentStart` → `subagent-start` (adds the citation-verification rules and the current `rewriteCycles.max` to the `auditor`'s context, and to no other subagent); `Stop` → `notify-stop` and `gate-enforce` (blocks ending the turn while a gate listed in the run's `requiredGates` is failing or missing); `SessionEnd` → `session-end-log`.

`aw` reads the key only from `GOOGLE_API_KEY` (`src/cli/src/gemini.ts`); `.academic-helper/secrets.json` is not a key source.

---

## `/academic-writer:setup` (`src/skills/setup/SKILL.md`)

`disable-model-invocation: true`: it runs only when typed.

| Step | What happens | Writes |
|---|---|---|
| 0 Preflight | `mkdir -p past-articles .academic-helper .academic-helper/logs`; copies `thresholds.json`. If a profile exists, offers "Check my Gemini key" (jump to 5f) or a full re-check. | folders |
| 2 Basics | `fieldOfStudy`, `targetLanguage`, `citationStyle` (`inline-parenthetical` / `chicago` / `mla` / `apa`). **Saves the profile immediately**, because `session-env` exports the key only when the profile exists. | `.academic-helper/profile.md` |
| 3 Detection | Runs the detection lines in `references/dependencies.md` and `references/python-deps.md` in parallel; shows a found / missing table. | none |
| 4 Tools | For each missing item: one-sentence explanation, `AskUserQuestion`, install only on "Install", re-detect. `python3 -m pip install --user python-docx lxml pdfplumber pymupdf jsonschema`; `brew install hspell` (Hebrew, macOS); `brew tap CandleKeepAgents/candlekeep && brew install candlekeep-cli`; `npm install -g notebooklm-mcp-cli`. Python and Homebrew get per-OS steps for the researcher; sign-ins (`! ck auth login`, `! nlm login`) are typed by the researcher. | none |
| 5 Gemini | Explains the key and the data flow, asks. Storage: plugin settings (`/plugin` → Installed → academic-writer → Configure → `google_api_key`, OS keychain) or a shell/user environment variable. Then restart. 5f runs `aw models check` (no network) and a `curl` to the Gemini models list with the key in the `x-goog-api-key` header (never printed, no article text). | `## Gemini` block |
| 6 Sample | 2 to 4 sentences written by Claude in the researcher's register. | none |
| 7–8 | Summary table; offers `/academic-writer:intro`, `/academic-writer:write`, `/academic-writer:init`. | profile |

Reference files: `src/skills/setup/references/{dependencies,python-deps,gemini-key,troubleshooting}.md`.

---

## `/academic-writer:init` (`src/skills/init/SKILL.md`)

`disable-model-invocation: true`. Phases: 0 Preflight (incl. the Python add-ons check) → 1 Integration detection (CandleKeep, NotebookLM) → 2 Profile (full name and `author_key`, field, language, citation style, abstract languages, writing style) → 3.5 Gemini onboarding (same reference as setup) → 3 Research sources (CandleKeep, shelf-scoped) → 4 Save profile.

- Style analysis: `extract-style-metrics.py` for computed metrics, then a qualitative pass; the researcher confirms the fingerprint before it is saved (`references/style-analysis.md`).
- Voice: reuses `${CLAUDE_PLUGIN_DATA}/voice/` when its `author_key` matches; otherwise runs `/academic-writer:voice`.
- `--quick` runs phases 0, 1, 2 and 3.5; style analysis becomes narrative-only, and sources are saved as `[]`.
- Profile format: YAML frontmatter (`name`, `author_key`, `fieldOfStudy`, `citationStyle`, `targetLanguage`, `abstractLanguages`, `analyzedArticles`, `createdAt`, `updatedAt`) plus `## Tools`, `## Output Format Preferences`, `## Style Fingerprint`, `## Article Structure`, `## Sources` and `## Gemini` JSON sections. Field-by-field: `src/skills/init/references/profile-schema.md`.

---

## `/academic-writer:write` (`src/skills/write/SKILL.md`)

Every `aw` call takes `--project-dir` and `--data-dir "${CLAUDE_PLUGIN_DATA}"` (required; `src/cli/src/paths.ts`) and one `--run <run-id>` shared by the whole article.

```text
Voice gate      python3 scripts/check-voice-populated.py AUTHOR_VOICE.md
                exit 0 → continue; exit 1 or 2 → STOP, ask for /academic-writer:voice
Voice load      voice-sync.sh pull "${CLAUDE_PLUGIN_DATA}" "$PWD"
Profile         cat .academic-helper/profile.md   (missing → ask for /academic-writer:init)
Guard           articles/<slug>.md exists → hand off to /academic-writer:edit
Steps 1–2       subject, language, length, optional user draft; source selection
                (ck items list, shelf-scoped); optional NotebookLM background (never cited)
W0 Intent       thesis in the author's words → .academic-helper/author-intent.json
W1 Evidence     aw evidence build → .academic-helper/evidence.json
                (only passages whose quotes match the source verbatim)
W2 Outline      architect agent → .academic-helper/outline.json; author approves each claim;
                aw decide outline.support (advisory, logged);
                python3 scripts/gate.py outline-v2 … must exit 0
W3 Draft        aw draft (background) → .academic-helper/drafts/<unitId>.md
                body units in dependsOn order, intro and conclusion last;
                code gates: citation-not-in-sources, quote-not-in-evidence,
                style-banned, style-capped, word-bounds (exit 2 → redraft)
W4 Audit        one auditor subagent per unit, in parallel; FAIL/PARTIAL →
                aw draft --unit <id> --feedback-file …; after rewriteCycles.max
                attempts the paragraph ships tagged [NEEDS REVIEW: …]
W5 Synthesize   aw synthesize: paragraph-level transition edits only, citations untouched
W6 Output       abstract and self-review (references/write-completion.md);
                aw docx → .academic-helper/runs/<id>/article.json → scripts/generate-docx.py
Handoff         author comments in Word → /academic-writer:revise
```

The auditor is the only mandatory hard gate and always runs. Jev decision points (`aw decide`, `write.audit_prescreen`, `write.voice_check`, `synthesize.needs_bridge`) are logged signals in shadow mode; none replaces the auditor or the author's approval.

---

## Files a first run creates

| Path | Created by |
|---|---|
| `past-articles/`, `.academic-helper/logs/`, `.academic-helper/thresholds.json` | setup / init preflight |
| `.academic-helper/profile.md` | setup Step 2, completed by init Phase 4 |
| `.academic-helper/research-brief.md` | ideate (optional) |
| `.academic-helper/author-intent.json`, `evidence.json`, `outline.json`, `drafts/` | write W0–W3 |
| `.academic-helper/runs/<id>/usage.jsonl` | every `aw` model call (`aw ledger show <run>` summarizes) |
| `.academic-helper/runs/<id>/article.json` and the `.docx` | write W6 |
| `${CLAUDE_PLUGIN_DATA}/voice/` | voice / init; shared by all projects, synced to CandleKeep |

---

## Error states and recovery

| State | Cause | Recovery |
|---|---|---|
| No profile | Setup never ran in this folder, or Claude Code was started elsewhere | `/academic-writer:setup` in the research folder |
| `missing Google API key` from `aw` | No key stored, no restart since storing it, or no profile when the session started | `/academic-writer:setup` → "Check my Gemini key"; restart in the research folder |
| Write stops at the voice gate | `AUTHOR_VOICE.md` missing, a stub, or unreadable | `/academic-writer:voice` |
| `gate.py outline-v2` exit 1 | An unapproved claim or an outline that does not match intent or evidence | Revise the outline or approvals, rerun the gate |
| `aw draft` exit 2 | A unit failed a code gate | Redraft that unit with a feedback file (counts as a rewrite cycle) |
| Paragraph tagged `[NEEDS REVIEW]` | Still failed the audit after `rewriteCycles.max` attempts | Check it by hand; named in the W6 report |
| Missing Python package | Add-ons not installed | `/academic-writer:setup`, or the pip line above |
| CandleKeep not signed in | CLI installed, no login | `! ck auth login` |

`/academic-writer:health` checks the profile, key, tools and sources and prints a fix line for each.
