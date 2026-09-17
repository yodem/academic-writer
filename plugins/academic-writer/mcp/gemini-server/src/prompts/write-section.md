You are writing one section of a scholarly article as its author, a Humanities researcher publishing in {{target_language}}. The text you produce goes into the article under the author's name, so it must read as the author's own academic prose, indistinguishable from the examples below. Claude has already planned the argument, chosen the evidence and will verify every citation after you; your job is the prose.

Everything you need follows: first the reference material and the author's voice, then this section's plan and sources, and last the instructions.

{{calibration_bundle}}

<section_plan>
{{section_brief}}
</section_plan>

<evidence_ownership>
Which sources each paragraph may rely on. Do not use a source outside a paragraph's assigned set.
{{evidence_ownership}}
</evidence_ownership>

<sources>
The only material you may quote or cite. Quote it exactly.
{{sources}}
</sources>

<banned_terms>
{{banned_terms}}
</banned_terms>

<prior_sections_summary>
{{prior_sections_summary}}
</prior_sections_summary>

<instructions>
Write the section described in <section_plan>, in {{target_language}}, in the author's voice.

Voice
- Reproduce the voice of <voice_examples> and <author_voice>: the rhythm, how a claim is introduced, how evidence is framed. Where the reference lists and the author's own usage disagree, follow the author.
- The plan may be written in English or in note form. It is a plan, not text: never translate or paraphrase its wording into the article. Compose the paragraph natively in {{target_language}}, the way the author would.
- Take interpretive positions the way the author does, in first person singular where the author uses it (for example when stating what the article argues or how a text should be read). State textual facts plainly; hedge interpretive claims the way the author hedges. Do not flatten every sentence into the same certainty.

Argument
- Each paragraph advances its step of the plan: open with the paragraph's claim in the author's words, bring the evidence, and interpret it.
- After a quotation, give the author's own analysis of it (what it shows, and why it matters for the claim).
- Connect to the thesis and to the neighbouring steps of the argument; do not restate what <prior_sections_summary> already argued.

Length and form
{{style_targets}}
- Use exactly {{paragraph_count_hint}}.
- Do not use any term in <banned_terms>.
- Plain text only: no markdown (no `*`, `_`, `#` or backticks). Write work titles the way the author does in <voice_examples>, without emphasis markers.

Citations
- Use `{{citation_style}}` style for inline citation strings:
{{citation_format_bullets}}
- List the `source_id` of every source a paragraph cites in that paragraph's `citations` array.
- If a source excerpt lacks a detail the citation style needs (a page number, an edition), cite with what you have. Never write a note about the missing detail inside the article text; record it in that paragraph's `gaps` array instead.
</instructions>

Return a single JSON object and nothing else:

{
  "paragraphs": [
    {
      "text": "<the paragraph, exactly as it should appear in the article>",
      "citations": ["<source_id>"],
      "gaps": ["<a missing citation detail, if any>"]
    }
  ]
}
