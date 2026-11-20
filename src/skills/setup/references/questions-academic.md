# Stage 2 Question Bank — Academic

This file is consumed by the `voice-interviewer` agent. The interviewer adapts within sessions
(12–18 questions, hard cap 18) but draws from this seed list. Also see `voice-interviewer.md`'s
"Confirm, don't compose" section — many `[T]` questions below should be asked as a fingerprint
confirmation rather than cold, when `.voice/fingerprint.md` already has a matching signal.

## Changelog — 2026 resumability redesign

Trimmed near-duplicate questions to cut composition burden without losing signal (the interview
still soft-floors at 12 and hard-caps at 18 per session; this just changes what fills those slots):

- **01 — Beliefs**: merged the two Hazal/transliteration questions into one (asking both angles in
  a single question costs one answer instead of two, and they were probing the same instinct).
- **05 — Structure**: cut "How do you signal a section break that isn't a heading?" — verbatim
  duplicate of 03's "How do you signal a beat change without a heading?"; one answer covers both.
- **06 — Refusals**: cut "Citation patterns dishonest-dressed-as-scholarly. Name three." — verbatim
  duplicate of 01's "What's a citation pattern that's dishonest dressed as scholarly?"; cut "Five
  'AI-coded' words" — near-duplicate of 03's Hebrew-specific version, which is more useful because
  it's language-scoped (banned-word lists must stay per-language, see `voice-distiller.md`'s
  compression principles). 07's "One AI-tell that survives even careful editing" stays — it's a
  distinct later-stage-editing angle, not a duplicate of either.

## Layer legend

- **[V]** Voice — Almaya-style, register/rhythm/refusals
- **[T]** Terminology — preferred/banned terms, transliteration, citation phrasing
- **[A]** Plugin-specific — academic register, thesis style, citation density, תקציר conventions

## 01 — Beliefs (voice-heavy)

- [V] Name one thing "good academic writing" is supposed to do that you think is bullshit. Defend.
- [V] What's a stylistic move you respect in writers you disagree with?
- [V] What's one belief about your field that you would defend in a footnote but not the main text?
- [T] Pick your Hazal-family convention (חז״ל / Hazal / Chazal / חז\"ל) for an audience using a
  different one, AND name one other standard transliteration you refuse regardless. Justify both.
- [A] When a source contradicts your thesis, do you preempt, footnote, cut, or restructure? Explain.
- [A] Is hedging ("arguably", "tends to") cowardice or rigor? Defend your answer.
- [V] One critique of your field that no insider has the standing to make.
- [A] What's a citation pattern that's dishonest dressed as scholarly? Three examples.
- [V] What does "rigorous" mean to you when nobody else is grading?
- [T] List five Hebrew academic terms you'd swap for plainer alternatives if the reviewer let you.
- [V] Productive contradiction: name two things you simultaneously believe that don't reconcile.

## 02 — Writing Practices (voice-heavy)

- [V] Describe what you do in the first 15 minutes of a writing session. Be specific.
- [V] Show me a sentence from your last article that you'd cut now.
- [V] When do you write fast vs slow? What's the visible difference in output?
- [T] List five phrases you use too often. Decide: keep, kill, or contextualize.
- [T] Three Hebrew connectives you overuse. Three you avoid.
- [A] When stuck on a thesis, what's the unblock — walk, sources, outline, coffee, person?
- [A] Citation density you aim for in a 7000-word article. Defend the number.
- [V] What's the smallest unit of writing you can produce in a sitting? Sentence, paragraph, section?
- [A] When you cite a source you disagree with, what's your typical framing verb?
- [V] One writing rule you've broken on purpose and would break again.
- [T] Phrases that signal "this writer is hedging because they're scared" vs "because they're rigorous".
- [V] What does revision feel like — pruning, surgery, reconstruction, polishing?

## 03 — Aesthetics (voice + plugin-specific)

- [V] Em-dash, semicolon, or comma — when each? Be specific.
- [V] Long sentences vs short. Default rhythm?
- [V] How do you signal a beat change without a heading?
- [T] Five words you refuse to use even when correct.
- [T] Five words that feel "AI-coded" to you in Hebrew academic prose.
- [A] Hedging quota in 7000 words: 0, ≤5, ≤15, unrestricted? Why?
- [A] Footnote density tolerance — what's "too many"?
- [V] One paragraph rhythm you've stolen from another writer.
- [T] What does תקציר sound like when it's working vs when it's filler?
- [A] Headings: numbered, not numbered, descriptive, declarative, question?
- [V] Two consecutive long sentences — when okay, when never?
- [T] What's a Hebrew word that's correct but you find ugly?

## 04 — Personality (voice-heavy)

- [V] When you're being honest in writing, what does that *sound* like? Show a sentence.
- [V] What does AI-generated writing sound like to you? Three specific tells.
- [T] Words that signal "me being earnest" vs "me hiding behind formality".
- [V] Emotional baseline — wry, severe, warm, clinical, urgent? One word, then defend.
- [V] One emotion you suppress on the page that shows up anyway.
- [V] Self-reference: first person, "we", impersonal? When each?
- [V] Humor: forbidden, allowed in footnotes, allowed inline, structural? Defend.
- [V] What's your default register with a hostile reader?
- [V] When you praise another scholar, do you sound generous or hedged?
- [V] One sentence you've written that you're proud of. Why.

## 05 — Structure (plugin-specific-heavy)

- [V] Average paragraph length. Why?
- [A] Section count for a 7000-word article. Defend.
- [A] Where does the תקציר go? What does it have to do?
- [A] Intro length as % of total. Conclusion length as % of total.
- [A] One section every paper of yours needs that most papers don't have.
<!-- Cut: "How do you signal a section break that isn't a heading?" — duplicate of 03's beat-change question. See changelog at top of this file. -->
- [A] Footnotes: explanatory, only citation, mixed, banned? Defend.
- [A] Section titles: declarative, descriptive, question, none?
- [V] How do you transition between sections — bridge sentence, blank line, summary?
- [A] When does a paragraph deserve to be one sentence?
- [T] Hebrew vs English heading numbering — different rules in your work?
- [A] What's the maximum nested-list depth you tolerate inside an article?

## 06 — Refusals (plugin-specific-heavy)

- [V] One sentence you would never write, even if a source demanded it.
- [V] Three opening sentences that are immediate cuts.
<!-- Cut: "Citation patterns dishonest-dressed-as-scholarly" — duplicate of 01's citation-pattern question. -->
- [A] Sources you would not cite even if relevant. Why?
<!-- Cut: "Five 'AI-coded' words" — near-duplicate of 03's Hebrew-scoped AI-coded question (kept there because banned-word lists must stay per-language). -->
- [T] Five Hebrew academic clichés you refuse.
- [V] Three closing sentences that are immediate cuts.
- [A] Tone you would never adopt — sycophantic, contemptuous, breezy, prosecutorial?
- [V] When would you walk away from an article rather than finish it?
- [A] What's a footnote you'd refuse to write even if a reviewer demanded it?

## 07 — Warning Signs (plugin-specific-heavy)

- [V] When you're writing badly, what's the first thing that goes wrong?
- [A] Fake-rigor red flags — what reads like scholarship but isn't?
- [T] Phrases that signal "this writer has stopped thinking".
- [V] Re-reading something you wrote, what makes you flinch?
- [A] One AI-tell that survives even careful editing.
- [V] When a draft is 80% there and won't get better, what do you do?
- [A] What's the difference between a paragraph that's wrong and one that's just unpolished?
- [V] Catastrophe signal — the moment you know to throw out the draft.
- [A] How do you know your argument is loose vs your prose is loose?
- [T] One Hebrew filler-word you use when you don't know what to say next.
