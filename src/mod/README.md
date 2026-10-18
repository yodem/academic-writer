# Activity pane (Claude Code mod)

A live pane that follows the newest Academic Writer run. Loaded through `src/hooks/hooks.json` `modules`
(`../mod/register.tsx`); the build copies this folder to `plugins/academic-writer/mod/`.

- `model.ts`: pure parsing and view logic (`parseEvents`, `viewOf`); no Claude Code imports; tested by `model.test.ts`
  (bundled by `src/cli/build-tests.mjs`, run with `npm run test:cli`).
- `register.tsx`: the hooks module. Pane id `aw-activity`; `/academic-writer:watch` opens it; it also opens unasked
  (engine places it only at 144+ columns) in a folder with `.academic-helper/profile.md` when `activity_pane` is true.
- Reads `.academic-helper/runs/<id>/activity.jsonl` with `$.fs` only while a run is active (2 s clock tick); `turn.complete`
  and `agent.spawn` only trigger a re-read. Torn or unknown lines are skipped. It never writes and never calls a model.
- Never name a local `h` in `register.tsx`: JSX compiles to calls of the global `h`.
- The live pane is checked by hand (on the Mac); everything else is covered by unit tests and `claude plugin validate`.
- Without the mod (older Claude Code), the `SubagentStop` hook prints the one-line status instead.
