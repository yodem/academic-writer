# academic-writer refactor: STATUS (2026-09-23, Mac lead)

**Branch:** `refactor/aw-step-engine` on origin, prepared as **0.14.0**. **Not merged to `main`, not released.**

## Tasks
| Task | State | Evidence |
|---|---|---|
| T1 runtime facts | accepted, merged | `docs/refactor/runtime-facts.md` (8 observed facts) |
| T2 construction fixes | accepted, merged | documented frontmatter keys, `omitClaudeMd` (about 20k tokens saved per subagent), no phantom agents |
| T3 measurement + eval | accepted, merged | `scripts/measure-run.py`, adversarial Hebrew fixture, context-anchored grader |
| T4 0.11.0 prep + install migration | accepted, merged | one user-scope install; 7 per-project installs removed (`docs/refactor/install-migration.md`) |
| T5 `aw` CLI core | accepted, merged | Gemini client with schema/finishReason checks, budgets, ledger, SessionStart key bridge |
| T6 judge providers | accepted, merged | isolated Pi/OpenRouter judge; Jev `decide()` (live call verified) |
| T7 proofread code core | accepted, merged | must-catch 14/14 on the fixture; geresh-aware guard; windowed anchoring |
| T8 proofread on `aw` | accepted, merged | live: names/terms 1.00, style 1.00, inside-quote 0, typo 0.77; 0 Claude tokens |
| T10 shared voice store | accepted, merged | the store in plugin data; `voice-sync.sh` backward-compatible |
| T11 evidence deep read | accepted, merged | verbatim-checked passages, cross-project source cache |
| T12 `/revise` docx loop | accepted, merged | reader exact on 3 real reviewed docx (every inserted/deleted character recovered) |
| T14 intent + outline v2 | accepted, merged (dev-server lead) | `gate.py outline-v2`, `aw decide` |
| T15a/T15b draft/synth/edit/ocr + MCP retirement | merged (lead-verified; split after ALE init) | live 2-unit draft: all gates pass, passage-id citations, predecessor bridge; live `aw edit` |
| T9/T13/T16 measure + release | **0.14.0 prepared, not released** | version-sync 6/6 agree; pytest 459; test:cli 55; smoke gate PASS (offline); `--live` FAILs only on typo 0.77 |

## Needs the author
1. **Typo recall 0.77 vs 0.85:** Gemini flash misses real-word errors. Options: (a) accept; (b) a stronger model for the wrong_word class; (c) relax the apply gate for verified medium-risk wrong_word fixes.
2. **Release:** merge `refactor/aw-step-engine` to `main`, push, then `claude plugin marketplace update academic-writer` and `claude plugin update academic-writer@academic-writer`. This also approves the MCP server retirement.
3. **T16 pilot:** write one real paper with `/write` in a fresh session and measure it with `scripts/measure-run.py` against the target (≤40M Claude tokens). Run `/revise` on your Word comments afterwards.
4. **Dev server:** install and log in to Codex, add `GOOGLE_API_KEY` to the shell environment, install hspell.

## Follow-ups (small)
- `src/skills/setup/references/troubleshooting.md` still mentions the MCP server in later sections.
- `scripts/build-plugins.sh` does not ship `src/schemas/`; gate.py uses drift-tested copies.
- The wrong-word second finder pass (`proofread.wrongWordPass`) measured no gain; remove it or keep it off.
