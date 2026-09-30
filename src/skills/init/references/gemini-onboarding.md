# Gemini Onboarding Detail (Phase 3.5)

> Read this when you reach Phase 3.5 (Gemini Onboarding) in SKILL.md. The key procedure itself is
> shared with `setup` in `${CLAUDE_PLUGIN_ROOT}/skills/setup/references/gemini-key.md`.

## Phase 3.5: Gemini Onboarding

Runs in both full and `--quick` modes. Ask the researcher whether to enable Gemini as the prose
writer for `/write`, `/edit`, and `/edit-section`. Claude remains the orchestrator and citation
auditor either way.

```python
AskUserQuestion(questions=[{
  "question": "Enable Gemini as the prose writer? Claude stays in charge of orchestration and citation audits — Gemini drafts and self-reviews paragraphs.",
  "header": "Optional — Gemini integration",
  "options": [
    {
      "label": "Yes, enable Gemini",
      "description": "Needs a free Google AI Studio key. Your article text is sent to Google for drafting.",
      "markdown": "```\nGemini ON\n─────────\n→ Faster, lower-cost drafting\n→ Per-language calibration gate runs\n   on first /write in each language\n→ Auditor still runs on Claude\n```"
    },
    {
      "label": "No, Claude only",
      "description": "Nothing is sent to Google; Claude writes and reviews everything.",
      "markdown": "```\nClaude only\n───────────\n→ No external API needed\n→ You can enable Gemini later via init\n```"
    }
  ],
  "multiSelect": false
}])
```

### If "No, Claude only"

Skip the rest of this phase. Note in summary that Gemini is disabled.

### If "Yes, enable Gemini"

All key handling follows `${CLAUDE_PLUGIN_ROOT}/skills/setup/references/gemini-key.md` (read it
now). In short: the plugin's `aw` command reads only the `GOOGLE_API_KEY` environment variable. The
plugin setting `google_api_key` is kept in the operating system's keychain and copied into that
variable by the start-up hook at the start of each session, in projects that have
`.academic-helper/profile.md`. A `.academic-helper/secrets.json` file is not read.

#### Step 3.5.a — Check for an existing key

```bash
[ -n "${GOOGLE_API_KEY:-}" ] && echo "KEY_PRESENT" || echo "NO_KEY"
```

`KEY_PRESENT` → go to 3.5.c. Never print the key.

#### Step 3.5.b — If NO_KEY, get and store one

1. Say the plain-language explanation from `gemini-key.md` (what an API key is, free tier,
   article text is sent to Google when Gemini is on, why the key must never be pasted in the
   chat).
2. Give the numbered steps to create a key at https://aistudio.google.com/apikey.
3. Ask where to keep it (the `AskUserQuestion` in `gemini-key.md § Storing the key`) and give
   the steps for the choice: `/plugin` → **Installed** → **academic-writer** → **Configure** →
   `google_api_key` (recommended, kept in the keychain), or the macOS / Windows / Linux shell
   profile steps.
4. Make sure `.academic-helper/profile.md` exists (write the Phase 2 fields now if Phase 4 has not
   run yet), so the start-up hook passes the key on after the restart.
5. Ask the researcher to quit and reopen Claude Code in this folder, then run
   `/academic-writer:setup` and choose **Check my Gemini key**, or re-run `/academic-writer:init`
   and choose Update. Finish the remaining init phases first if they prefer; the key check can
   wait.

#### Step 3.5.c — Check the key

Run the two checks in `gemini-key.md § Checking the key` (`aw models check`, then the live check
that sends no article text) and give the researcher the matching plain-language line.

#### Step 3.5.d — Note the opt-out check

> "Gemini is on by default for `targetLanguage` (`{targetLanguage}`). If you'd rather compare it
> against Claude first, you can run the optional model-comparison check any time — it shows one
> Claude paragraph and one Gemini paragraph on the same topic and lets you opt a language back out
> of `gemini.approvedLanguages` if you prefer Claude's output."

#### Step 3.5.e — Store Gemini settings

The `## Gemini` block in `profile.md` (written in Phase 4 below) is seeded with `targetLanguage`
already approved — Gemini is default-on for the language the researcher is about to write in, so a
project that only ever proofreads or edits (and never runs `/write`'s model-comparison check)
still gets Gemini:

```json
{
  "enabled": true,
  "approvedLanguages": ["{targetLanguage}"],
  "models": {}
}
```

If the researcher chose "No, Claude only": `enabled: false`, `approvedLanguages: []` (Gemini
is off entirely, so there is nothing to approve).
