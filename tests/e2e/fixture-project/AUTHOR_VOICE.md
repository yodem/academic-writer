# AUTHOR_VOICE — E2E Fixture

Deterministic voice profile for the dual-path end-to-end demonstration. Both the Gemini run and
the fallback run read this same file, so any difference in output is attributable to the engine,
not the voice profile.

## Core voice

- Formal academic Hebrew; expository, analytical register.
- Sentences average ~24 words; willing to use a longer subordinate clause when developing an argument.
- Paragraphs open with a leading claim, develop it against a cited source, and close with a forward link.
- Prefers causal and contrastive connectives (לפיכך, אולם, מכאן ש, יתרה מזו).
- No colloquialisms, no rhetorical questions in body prose, no first person plural beyond the framing intro/conclusion.

## Academic-specific

- Every interpretive claim is anchored to a specific textual feature of the cited source.
- Citations are inline-parenthetical in Hebrew: `(אוגוסטינוס, וידויים, עמ' 11)`.
- Translated/foreign authors keep their name; surrounding prose stays in Hebrew.
- Never infer bibliographic metadata — use only what `sources.json` provides.
