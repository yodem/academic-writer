# 0006. PageIndex stays an optional local route; next steps are an eval run and a newer pin

Status: accepted (assessment, 2026-11-26; no code change). Sources: pageindex.ai/docs, pageindex.ai/pricing,
pageindex.ai/docs/changelog, github.com/VectifyAI/PageIndex README, docs/library-routes.md, PINNED.json.

## Context
PageIndex now has four surfaces: the MIT open-source tree builder (local, text-based PDFs only), a paid Cloud
(Agent, Page Search and Page Extract APIs, which read scanned pages visually with no OCR step), a hosted MCP server
and a chat app. Retrieval works the same way in each: an LLM reasons over a table-of-contents tree with section
summaries, with no embeddings. The plugin already uses the local builder: per-project Trove, PageIndex or Both routes
(Both runs a quiet shadow test), `aw library install|index|backfill`, the ingest dual-write, the retrieval ledger and
the blind evaluation. The pinned commit is af92d96 (2026-10-12), 101 commits behind upstream main on 2026-11-26.

## Findings
- Fit: the local builder fits the plugin's rules. It runs on the researcher's machine, needs no PageIndex key and
  indexes from Trove's existing hints. In our own small samples (the published Trove-vs-PageIndex comparison, not
  reproducible from this repo), the table-of-contents page ranges mattered more than the engine: on the Hebrew
  Bible, Trove scored 1/5 against 5/5 for PageIndex with hints, because a Trove range ended one page early. On an
  English book and on Ashkenazi Hebrew sources the two tied.
- Gap: the blind evaluation has never been run on a real article, so the route choice rests on small samples.
- Gap: since our pin, upstream has added a mode that calls Claude through the researcher's own Claude Code
  subscription (`claude-code/` models, 2026-10-18). Our summaries do not use upstream's model dispatcher: pilib's
  summarizer calls `litellm.completion` directly. Subscription summaries, which would match ADR 0003's own-tools
  rule, therefore need their own integration in pilib (metering, consent, failure handling), apart from any re-pin.
- Gap: Trove-only ingest skills outside the plugin skip both the dual-write and a check of the page ranges.
- Not adopted: Cloud, the hosted MCP server and the chat app. They need an API key and keep uploaded documents
  until the researcher deletes them. They publish no Hebrew or right-to-left support and no humanities benchmark:
  every vendor benchmark uses financial filings and was run by Vectify. Scanned pages already go through `aw ocr`.

## Decision
Keep Trove as the default and PageIndex as the optional local route, and keep the rule against Cloud. Next:
(1) run `/academic-writer:library library-eval` on one real article before changing any default; (2) at ingest,
check each section's range with pilib's own rule (native.py): it ends on the page before the next entry at the
same or higher level starts (on that page itself when both start there, never before its own start), includes
its children, and the last one runs to the end of
the book; this helps both routes; (3) re-pin PageIndex, and separately add Claude-subscription summaries in pilib
beside Gemini and `--summaries hints`.

## Consequences
- No vendor accuracy figure is quoted in the plugin or its docs.
- Re-pinning requires recompiling the hashed locks and passing the pageindex tests.
