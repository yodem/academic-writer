# Setup finish: sample paragraph and next steps

> Loaded by `setup` Step 6 and Step 8. Both follow rule 3 (a question's text is the only text sure to be seen).

## Step 6 — Sample paragraph

A quick proof that the conversation works, not a full article. The paragraph must reach the researcher's eyes
before they are asked about it (rule 3), so this step takes **two turns**.

**Turn 1.** Ask for a topic:

```python
AskUserQuestion(questions=[{
  "question": "Let's write one short sample paragraph so you can see it working. Give me a small topic (choose \"Other\" to type it, e.g. \"the printing press\"), or I'll pick one.",
  "header": "Sample",
  "options": [
    {"label": "Pick one for me", "description": "I'll choose a general topic in your field."},
    {"label": "I'll type a topic", "description": "Then choose Other and type it."}
  ],
  "multiSelect": false
}])
```

**Turn 2.** Write 2-4 sentences on that topic, in the register of `fieldOfStudy` and in `targetLanguage`, and ask
about them with the paragraph **inside the question text** (the choice stays visible with it):

```python
AskUserQuestion(questions=[{
  "question": "Here is your sample paragraph:\n\n<THE 2-4 SENTENCES>\n\n(Real articles cite your sources and follow your own voice, which /academic-writer:init learns from your past articles.) Does the tone look like what you'd expect?",
  "header": "Tone check",
  "options": [
    {"label": "Yes, looks good", "description": "Setup is complete."},
    {"label": "Not quite", "description": "Tell me what's off; I'll note it. It doesn't block anything."}
  ],
  "multiSelect": false
}])
```

If the paragraph is long, print it, end the turn with "Tell me what you think of it", and take the answer in
plain chat instead. Either answer completes setup.

## Step 8 — What you can do now

Re-run `setup_checks.py --json` once more, then print a short block (at most 8 lines, plain words, in
`targetLanguage`) for the researcher's `role`. Give each command with one concrete sentence about what to do.
List only commands whose prerequisites passed in that run, and leave out the rest instead of apologising for them.
Always end with `/academic-writer:intro`. This block is the last thing printed before Step 9's question, so
**end your turn after it** and ask Step 9 in the next turn (or fold the list into Step 9's question text).

| Role | Candidate commands | Needs |
|---|---|---|
| Student | `/academic-writer:courses` (set up a term), `/academic-writer:lesson-notes`, `/academic-writer:dashboard`, `/academic-writer:write` | `courses` and `dashboard`: home folder; `lesson-notes`: `trove`; `write`: `gemini-key` |
| Researcher | the three steps below | see below |
| Lecturer | `/academic-writer:courses`, `/academic-writer:dashboard`, then the researcher list | as above |

**Researcher block (use this wording, translated to `targetLanguage`):**

> 1. **Teach it your style:** copy 5 to 10 of your published articles (PDF or Word) into the `past-articles`
>    folder inside this project folder (open it in Finder: Cmd+Space, or right-click the folder), then type
>    `/academic-writer:init`. It reads them and shows you what it learned so you can correct it.
> 2. **Write an article:** type `/academic-writer:write`; I ask one question at a time and you decide the thesis and outline. (Needs the Gemini key.)
> 3. **Research your sources:** add them to Trove with `/academic-writer:ingest`, then ask with `/academic-writer:research`. (Needs Trove.)
> 4. Illustrated guide: `/academic-writer:intro`.

Drop step 2 if `gemini-key` failed and step 3 if `trove` is missing, and add one line naming the missing step
that would unlock the most (for example "add the Gemini key by running `/academic-writer:setup` again").
If nothing but `/academic-writer:intro` qualifies, say that and name that one step.
