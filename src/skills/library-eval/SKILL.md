---
name: library-eval
description: "Compare Trove and PageIndex on your own article: pick claims from a draft, let each library find the supporting pages, then judge anonymised A/B pairs yourself on a private page, and see the unblinded results (win rate, cost, time, agreement with the citation checker). Use when the author wants to know which library finds the right pages better for their own sources, after a draft with footnotes exists and the sources are in both libraries. Do NOT use to change which library an article reads from (use /academic-writer:update-tools) or to add books (use /academic-writer:ingest or /academic-writer:ingest-book)."
user-invocable: true
allowed-tools: [Bash, Read, Write, AskUserQuestion]
metadata: {author: "Yotam Fromm", version: "0.1.0", summary: "Compare Trove and PageIndex on your own article: anonymised pairs you judge yourself, then the unblinded results."}
---

# Compare the two libraries on your article

The author decides which library finds the right pages better by judging real results **without knowing which library produced which**. The plugin picks claims from the article's draft, asks a separate Claude (or Codex) helper to find the supporting pages in each library, shows the two answers side by side as "A" and "B" in random order, and only after the author has judged every pair reveals which was which, with the numbers.

The rule the whole skill serves: **the author never sees which library is A or B until the judging is finished, and neither do you in your messages.** Everything is deterministic code (`aw library eval ...`); you run it and report plainly.

## 1. Pre-flight

1. Read `.academic-helper/profile.md`. If it does not exist, say nothing is set up yet and point at `/academic-writer:setup` or `/academic-writer:init`; stop.
2. Check both libraries answer:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" library status --check
```

   In the JSON, `check.trove.ok` and `check.pageindex.ok` must both be `true`. If PageIndex is not set up, point at `/academic-writer:setup` (it offers the built-in helper) and stop. If Trove or PageIndex fails, show its `error` in plain words and stop.
3. There must be a draft with footnotes under `.academic-helper/drafts/` (or the author gives a list of claims with `--claims`). Without one, say so and point at `/academic-writer:write`; stop.
4. The helper that locates pages is the `claude` program (Claude Code), or `codex` if the author prefers it. If neither is on the path (`command -v claude`, `command -v codex`), say this comparison needs Claude Code or Codex and stop.
5. The sources of the claims must be in **both** libraries. A source that is only in Trove is skipped with a reason; if that leaves no claims, offer to prepare the books for PageIndex (`/academic-writer:update-tools`, "prepare existing books") and stop.

## 2. Plan: pick the claims

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" library eval plan \
  --article <draft-path-or-run-id> [--n <claims>] [--seed <text>] [--claims <your-claims.json>]
```

It prints one JSON line: `eval_id` (use it in every later command), `claims`, `runs`, `estimated_usd` and `skipped` (claims left out, with reasons). Tell the author in plain words how many claims were picked and from how many sources, and what was skipped and why. `--n` sets how many claims; the code keeps it within its limit. A claim picked from the draft is a sentence with a footnote, joined to the source and printed page it cites. A footnote may name its source by id or, as in a real article, by author and title ("Pedersén, South Palace Archives, 14.", "Ibid.", "שם"); the code matches it to `sources.json` and never guesses. When the output has `unmatched_notes`, tell the author how many footnotes could not be matched and why (the first few are printed, all are in `unmatched-notes.json` in the evaluation folder): usually a work that is not in `sources.json` yet, or two works by one author that the note does not tell apart.

## 3. Ask before anything is spent

Ask with `AskUserQuestion`. Say, from the plan output: how many helper runs (`runs`: each claim is searched once in each library), the estimated cost (`estimated_usd`; it is an estimate: the real figure is reported at the end), that the claims and the page text they find go to Anthropic as with any Claude use (or to OpenAI if Codex is chosen), that it runs on the author's own Claude (or Codex) plan, and that it takes a while. Options: **Run it with Claude** (default), **Run it with Codex** (only if installed), **Not now** (the plan is kept; nothing is spent).

## 4. Run: locate the pages in each library

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" library eval run \
  --eval <eval_id> [--engine claude|codex] [--parallel <n>]
```

This can take many minutes: run it in the background (the Bash tool's `run_in_background`) and check progress with `library eval status --eval <eval_id>` (it shows stage, runs finished and failed, and never names a library). Running it again continues where it stopped: finished runs are skipped. The output is `planned`, `done`, `skipped`, `failed`, `invalid` and `cost_usd`; report those only, in plain words. A few failed runs are normal; the same command retries them. **Invalid runs are different and come first in your report:** when `warning` or `invalid_runs` is present, an agent ran a command outside its two allowed ones (for example a pipe such as `| head`), so its answer was thrown away and its claim is left out of the pairs. Say how many runs and which claims, and why (`reason`), without naming a library. `library eval status` shows the same under `invalid`. Too many invalid runs leave too few pairs to judge; run again with `--reset` only if the author agrees (it costs again).

## 5. Build the pairs and the judging page

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" library eval pairs --eval <eval_id>
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" library eval page --eval <eval_id>
```

`pairs` anonymises the answers: both sides show page text taken the same way, so only the **choice of pages** differs; pairs where both libraries chose exactly the same pages are recorded as "same" and not shown. The sealed key is kept in a separate file. `page` prints the path of `judge.html` inside the evaluation folder (`.academic-helper/library-eval/<eval_id>/`).

**Do not open `.academic-helper/library-eval/<eval_id>/sealed/` or the `runs/` folder, and do not read results out of any file, until the unblind step.** Do not guess or hint which side is which.

## 6. The author judges

Ask with `AskUserQuestion` how to judge:

- **A file on this computer** (always works): tell the author to open `judge.html` with a double click, read each claim and the two answers, choose "Better: A", "Better: B", "Same" or "Neither" (with an optional note), and press "Download judgments" at the end. Then ask for the path of the downloaded `judgments-<eval_id>.json`. The page remembers answers in the browser, so it can be done in several sittings.
- **A private page on claude.ai** (only when this session can publish pages): the claims and page excerpts would go to claude.ai, so ask first and say so. Publish `judge.html` as a private page that keeps its answers on the page itself, give the author the link, and when they say they are done read their answers back into a judgments file in the shape below. If this session cannot publish pages, or the page has no saving built in, offer the file option instead.

The judgments file shape: `{"eval_id": "<eval_id>", "judgments": [{"pair_id": "...", "verdict": "A|B|same|neither|skip", "note": "...", "at": "<time>"}]}`.

## 7. Import and unblind

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" library eval import --eval <eval_id> --file <judgments-file> [--partial]
```

Import refuses a file that leaves pairs without a judgment: the author can mark them "skip" on the page, or you add `--partial` to save progress now and import the rest later. Then:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/aw" --data-dir "${CLAUDE_PLUGIN_DATA}" --project-dir "$PWD" library eval unblind --eval <eval_id>
```

Never add `--force`: unblinding before the judgments are in is refused on purpose, and the author's own judging comes first.

## 8. Report in plain words

`unblind` prints the report and saves `report.md` and `report.json` in the evaluation folder. Summarise it for a researcher with no technical background:

- For each library: pairs won, lost, tied ("same") and "neither", the win rate among decided pairs, and how sure that is. The report states the number of judged pairs and an exact test; when there are too few pairs for a verdict the report says so, and **you must not turn it into "library X is better"**.
- What each library cost and how long it took per claim (the figures come from the helper runs, not estimates), and how much page text each returned.
- Agreement with the citation checker: how often each library found the page the checker had confirmed, and whether the author's choices agree with that.
- A list of the pairs with the author's own notes, now with the libraries named.

State limits honestly: the blinding protects the author as a judge; the helper's answers are for this article's sources only; a small number of pairs is a hint, not proof. Offer to repeat on another article, or to change which library an article reads from (`/academic-writer:update-tools`). The retrieval report (`aw library report --eval <eval_id>`) adds returned-text sizes and per-library timing from the same runs.
