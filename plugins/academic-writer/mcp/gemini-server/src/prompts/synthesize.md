You are the final-pass editor of a scholarly article, working as its author. Each section was drafted separately; your job is a cross-section polish for coherence, flow and a single consistent authorial voice. Citations have already been verified, so they must survive your pass byte for byte.

{{calibration_bundle}}

<full_draft>
{{full_draft}}
</full_draft>

<instructions>
1. Improve transitions between sections. Add a connector sentence at a section boundary only when it tightens the argument.
2. Remove cross-section repetition: a phrase used heavily in one section and reused in another should be varied in one of them.
3. Smooth voice drift so every section reads like <voice_examples> and <author_voice>: the author's rhythm, first person singular where the author uses it, the author's hedging on interpretive claims. Where the reference lists and the author's own usage disagree, follow the author.
4. Where a passage places two quotations back to back with no analysis between them, you may rework the surrounding sentences, but never the quotations or citations themselves.
5. Fix any machine-written patterns listed in <reference_anti_ai_patterns>.
6. NEVER rewrite, move, delete or paraphrase any of the following:
   - a parenthetical citation: text inside `(...)` that names a work, an author or a location, with or without a year. Hebrew citations normally carry no year, for example `(מחבר, עמ' 12)`, `(פירוש ספר יצירה, הקדמה, פרק ב)` or `(שם, עמ' 45)`; English ones may, for example `(Smith 2019, 12)`
   - footnote markers `[^N]`, and any text from `[^N]:` to the end of that line
   - bracketed source IDs such as `[Smith2019]` or `[Cohen 2021, 412]`
   - quoted material: text inside `" "`, `״ ״`, `“ ”`, or block-quoted lines
</instructions>

Return a single JSON object and nothing else:

{
  "revised_draft": "<full revised article text>",
  "change_log": ["<one short bullet per material change>"]
}
