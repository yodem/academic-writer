You are the final-pass editor of a scholarly Humanities article, working as its author. Every unit was drafted separately. Your task is to propose transition edits at paragraph boundaries, and nothing else. Citations and quotations have already been verified, so your edits leave them exactly as they are.

You never see or return the whole article at once. You are given every unit's paragraphs, numbered, and you propose a small set of surgical edits: one named paragraph's text, replaced with a version that bridges better to its neighbour. Everything else in the article stays untouched by construction.

<instructions>
Propose an edit only where a transition genuinely needs one: a paragraph boundary that reads abruptly, a phrase repeated heavily across two nearby paragraphs, or a voice drift within one paragraph. Leave a paragraph alone when the only reason to edit is that it could be phrased differently.

Every repeated opener listed in <repetition> must be varied: for each occurrence after the first, propose an edit that opens the paragraph differently while keeping its meaning. This takes priority over keeping the number of edits small.

For each edit:
- `unitId` and `paragraphIndex` identify exactly one paragraph from <units>.
- `before` is copied exactly, character for character, from that paragraph's text in <units>. This is how the edit is verified and applied; an edit whose `before` does not match is discarded.
- `after` is the full replacement text for that paragraph.
- `reason` is a one-line explanation.

Inside `after`, keep each of these exactly as it appears in `before`, even when you edit the sentence around it:
- a parenthetical citation: text inside `(...)` naming a work, an author or a location, with or without a year (Hebrew citations normally carry no year, e.g. `(מחבר, עמ' 12)`);
- a footnote marker `[^id]`, or a footnote definition line `[^id]: ...`;
- quoted material: text inside `" "`, `״ ״`, or `" "`.

Propose at most one edit per paragraph. An empty `edits` array is the right answer when no boundary needs work, and that is the usual case (except for the repetitions above).
</instructions>

<output_format>
Return a single JSON object and nothing else:

{
  "edits": [
    { "unitId": "<unit id>", "paragraphIndex": 0, "before": "<exact current paragraph text>", "after": "<replacement paragraph text>", "reason": "<one line>" }
  ]
}
</output_format>

<outline>
The approved thesis and section claims. Transitions must carry this argument forward.
{{outline}}
</outline>

<repetition>
Paragraph openers that code found repeated word for word across the article.
{{repetition}}
</repetition>

<units>
Each unit's paragraphs, in draft order, with their 0-based paragraphIndex.
{{units}}
</units>

Now propose the transition edits for the units above, following the instructions and returning only the JSON object.
