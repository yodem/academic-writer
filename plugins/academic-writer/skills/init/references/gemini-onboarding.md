# Gemini Onboarding Detail (Phase 3.5)

> Read this when you reach Phase 3.5 (Gemini Onboarding) in SKILL.md. It has the full key-check,
> key-creation, live-probe, and settings-storage procedure.

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
      "description": "Requires a Google AI Studio API key (free tier available).",
      "markdown": "```\nGemini ON\n─────────\n→ Faster, lower-cost drafting\n→ Per-language calibration gate runs\n   on first /write in each language\n→ Auditor still runs on Claude\n```"
    },
    {
      "label": "No, Claude only",
      "description": "Today's behavior — Claude writes and reviews everything.",
      "markdown": "```\nClaude only\n───────────\n→ No external API needed\n→ You can enable Gemini later via init\n```"
    }
  ],
  "multiSelect": false
}])
```

### If "No, Claude only"

Skip the rest of this phase. Note in summary that Gemini is disabled.

### If "Yes, enable Gemini"

#### Step 3.5.a — Check for existing key

This only checks the two shell-visible sources — the plugin's own secure configuration option
(preferred; see 3.5.b) is resolved by the MCP server process and isn't visible to this shell check.
`NO_KEY` here means "not found at the shell level," not "not configured anywhere" — 3.5.c's live
probe is authoritative:

```bash
if [ -n "$GOOGLE_API_KEY" ]; then
  echo "Found GOOGLE_API_KEY in environment."
elif [ -f .academic-helper/secrets.json ] && python3 -c "import json,sys; sys.exit(0 if json.load(open('.academic-helper/secrets.json')).get('GOOGLE_API_KEY') else 1)" 2>/dev/null; then
  echo "Found GOOGLE_API_KEY in .academic-helper/secrets.json."
else
  echo "NO_KEY (at the shell level — try the 3.5.c probe before assuming nothing is configured)"
fi
```

#### Step 3.5.b — If NO_KEY, walk through key creation

> "To get a Google AI Studio API key:
> 1. Open https://aistudio.google.com/apikey in your browser
> 2. Sign in with a Google account
> 3. Click 'Create API key' — copy the key (it begins with `AIza...`)
> 4. Free tier covers typical academic-writer usage."

Ask how to store the key:

```python
AskUserQuestion(questions=[{
  "question": "Where should I store your Gemini API key?",
  "header": "Key storage",
  "options": [
    {
      "label": "Plugin configuration (recommended)",
      "description": "Stored securely by Claude Code (OS keychain / protected credentials file) — never plaintext.",
      "markdown": "```\nclaude plugin install academic-writer --scope project \\\n  --config google_api_key=\"AIza...\"\n\n# Already installed? Reconfigure via the /plugin\n# manager, or:\nclaude plugin config academic-writer \\\n  --config google_api_key=\"AIza...\"\n```"
    },
    {
      "label": "Environment variable",
      "description": "Set GOOGLE_API_KEY in your shell profile. Survives across projects.",
      "markdown": "```\nexport GOOGLE_API_KEY=\"AIza...\"\n# add to ~/.zshrc or ~/.bashrc\n```"
    },
    {
      "label": "Project-local secrets file",
      "description": ".academic-helper/secrets.json (gitignored, this project only).",
      "markdown": "```\n.academic-helper/secrets.json\n──────────────────────────────\n{ \"GOOGLE_API_KEY\": \"AIza...\" }\n→ Already in .gitignore\n```"
    }
  ],
  "multiSelect": false
}])
```

- **Plugin configuration path**: print the `claude plugin install`/`claude plugin config` command (or point at the `/plugin` manager) for the user to run outside this conversation, then ask them to confirm and restart Claude Code. You cannot run this on their behalf or open the config dialog from inside Claude Code.
- **Env var path**: print the export command for the user to run. Then ask them to confirm they've set it and reopened the session so Claude Code picks up the env. You cannot set their shell env from inside Claude Code.
- **Secrets file path**: ask them to paste the key, then:

```bash
mkdir -p .academic-helper
python3 -c "
import json, pathlib, os
p = pathlib.Path('.academic-helper/secrets.json')
data = json.loads(p.read_text()) if p.exists() else {}
data['GOOGLE_API_KEY'] = os.environ['_PASTED_KEY']
p.write_text(json.dumps(data, indent=2))
import stat
p.chmod(stat.S_IRUSR | stat.S_IWUSR)
"
```

(Pass the pasted key via env var to avoid leaking it through shell history.) Confirm `.academic-helper/secrets.json` is gitignored.

All three paths coexist — the server checks the plugin configuration first, then the environment
variable, then the secrets file, so picking one doesn't disturb whichever else may already be set.

#### Step 3.5.c — Probe the key

Run a one-shot probe through the MCP server to verify the key works end-to-end:

```
mcp__gemini-api__gemini_raw({
  system: "Reply with exactly the word PONG and nothing else.",
  prompt: "PING"
})
```

- On success (returned `text` contains "PONG"): print "✓ Gemini API key verified."
- On `{ error: { code: "no_credentials" } }`: print "Key not detected by the MCP server. If you just set the plugin configuration or the env var, restart Claude Code so the server inherits it. Re-run `/academic-writer:init` after restart."
- On any other error: print the error and tell the user Gemini will not be available until resolved.

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
