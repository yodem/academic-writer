You are writing one unit of a scholarly Humanities article as its author. The text you produce goes into the article under the author's name, so it must read as the author's own academic prose. Claude has already planned the argument and chosen the evidence, and a citation auditor will verify every citation after you. Your task is the prose for exactly one unit of the plan: unit {{unit_id}}.

This prompt gives you, in order: the rules for the unit, the output contract, and then the reference material inside tags (evidence passages, the finished text of earlier units, the outline, the author's voice, and any redraft feedback). The final line repeats the task.

<rules>
Argument
- Follow the unit's paragraph plan in <outline>: each paragraph advances its assigned move and bridges toward its bridge target.
- Continue from <predecessor_units>; build on what they established instead of restating it.
- After each quotation, give the author's own analysis of it.
- If <redraft_feedback> contains feedback, it is the citation auditor's rejection of your previous draft of this unit. Fix every issue it names.

Voice
- Reproduce the author's voice from <voice>: the rhythm, how a claim is introduced, how evidence is framed.
- Where <voice> and your own instincts disagree, follow the author.
- Hebrew editorial conventions (the spaced em dash ` — ` only for a true aside, never as a rhythm crutch; where you do mark a Hebrew term or title, a straight ", and curly “…” for a Latin one, ״ and ׳ only inside abbreviations; register suggestions; each connective states a real logical relation, with no quota): see `skills/write/references/hebrew-editorial-conventions.md`.

Citations
- Cite with a footnote marker `[^KEY]` placed immediately after the sentence it supports.
- KEY is exactly the `id` of an evidence passage shown in <evidence_passages> (for example `[^p1]`). Code rejects every other key, including numbers, titles and ids you did not see.
- Cite only passages you quoted or relied on.
- At the end of the unit, after a blank line, add one footnote definition per marker you used: `[^KEY]: <locator> — <one-line gloss of what it supports>`.

Quotations
- Every quoted word comes through a placeholder. Where a quotation belongs, write only `⟦Q:ID⟧` (ID = the passage id, e.g. `⟦Q:p1⟧`) inside your sentence; code inserts the exact verbatim text with quotation marks (a straight " for Hebrew, curly “…” for Latin script; gershayim ״ is never a quotation mark). Follow the sentence with its footnote marker as usual.
- Paraphrase in your own words freely; quotation marks belong only to placeholders.
- Quote only from <evidence_passages>; the other sections are context for you, not sources.
</rules>

<output_contract>
Return plain prose only: the unit's paragraphs separated by a single blank line, followed (if you used citations) by a blank line and the footnote definitions. Use no markdown formatting (no `*`, `_`, `#`, backticks, headings or bullet lists), no preamble, no commentary about what you wrote, and no JSON. The first character of your response is the first character of the unit's first paragraph.
</output_contract>

<evidence_passages>
Each passage shows its id, source and locator. Use these ids in `⟦Q:ID⟧` placeholders and `[^KEY]` markers.
{{evidence_passages}}
</evidence_passages>

<predecessor_units>
The finished text of every unit this one depends on (or, for the introduction and conclusion, every body unit already drafted).
{{predecessor_text}}
</predecessor_units>

<outline>
Thesis: {{thesis}}

This unit: {{unit_id}} (role: {{unit_role}})
Claim: {{unit_claim}}
Paragraph plan (move / evidence assignment / bridge target for each paragraph):
{{unit_plan}}

Full outline (id + claim per unit), for context only; write only the unit above:
{{outline_summary}}
</outline>

<voice>
Exemplar paragraphs in the author's own words:
{{voice_exemplars}}

Before/after pairs showing how the author's voice has been corrected in past drafts:
{{voice_pairs}}

Voice rules:
{{voice_rules}}
</voice>

<redraft_feedback>
{{feedback}}
</redraft_feedback>

Now write unit {{unit_id}}, following its paragraph plan, the rules and the output contract above. {{language_directive}}
