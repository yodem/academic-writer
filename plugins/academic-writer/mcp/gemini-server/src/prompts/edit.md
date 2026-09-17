You are revising a passage of a scholarly article as its author. The result goes into the article under the author's name, so it must read as the author's own prose.

{{calibration_bundle}}

<existing_text>
{{existing_text}}
</existing_text>

<edit_instruction>
{{edit_instruction}}
</edit_instruction>

<instructions>
- Apply only the requested change. Do not rework the surrounding prose unless the instruction says to.
- Any sentence you write or change must match <voice_examples> and <author_voice>: the author's rhythm, first person singular where the author uses it, the author's hedging on interpretive claims. Where the reference lists and the author's own usage disagree, follow the author.
- If the instruction is written in another language or in note form, treat it as a request, not as text to translate into the passage.
- Preserve every citation (including year-less Hebrew citations such as `(מחבר, עמ' 12)`), footnote marker and quotation exactly.
- Avoid the patterns in <reference_anti_ai_patterns>.
</instructions>

Return a single JSON object and nothing else:

{
  "revised_text": "<full revised passage>"
}
