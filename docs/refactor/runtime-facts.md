# Plugin runtime facts (T1 spike, 2026-09-23)

Observed on the Mac with Claude Code 2.1.280, a throwaway probe plugin loaded with `claude -p --plugin-dir`, pi 0.85.1 and jev-ask. The probe plugin lived in the session scratchpad and is not in the repo. Every answer below comes from an observed command and its output.

## DATA_DIR_RESOLUTION
A skill body containing `aw-probe "${CLAUDE_PLUGIN_DATA}" "${CLAUDE_PLUGIN_ROOT}"` produced:
```
ARG1=~/.claude/plugins/data/awprobe-inline
ARG2=<path of the plugin dir>
```
The same script's environment matched nothing for `CLAUDE_PLUGIN|USER_CONFIG|OPTION|CLAUDE_PROJECT`: the grep printed no lines. So Bash subprocesses do **not** receive the plugin variables. Claude Code substitutes them into skill text, and the skill has to pass them to `aw` as arguments (`aw --data-dir "${CLAUDE_PLUGIN_DATA}" ...`).
Answer: skill-substitution-arg

## KEY_RESOLUTION
With the option unset, `${user_config.probe_plain}` in a skill body reached the shell as literal text:
```
(eval):1: bad substitution
```
No plugin option environment variables reach `bin/` subprocesses (see above), and sensitive values are never substituted into skill content (per the docs). So `aw` cannot receive `google_api_key` or `jev_api_key` from userConfig directly: keys must come from the environment. Candidate bridge for T5: a SessionStart hook, which does receive `${user_config.*}` in its command env, writes `export` lines to `$CLAUDE_ENV_FILE`. **Unverified.** T5 must test it before relying on it.
Answer: env-only

## FORK_MODEL
Running a skill with `context: fork` and `model: sonnet` reported two models in `modelUsage`:
```
models: ['claude-opus-5-5[1m]', 'claude-sonnet-5']
```
The forked subagent ran on Sonnet. **Caveat for T8.** Twice, the forked subagent refused to run a bundled `bin/` script named only in the skill body, calling it an untrusted instruction. The second refusal cited passing a `user_config` value. A forked skill that must run `aw` needs a body that states plainly that the command is the skill's purpose, and no secret-looking arguments.
Answer: yes

## OMIT_CLAUDE_MD
Two otherwise identical Haiku agents were asked whether they could see the project CLAUDE.md:
```
omit   (omitClaudeMd: true)  -> "NO"   haiku tokens 28786
withmd (no omitClaudeMd)     -> "YES"  haiku tokens 49055
```
That is about 20k tokens saved per spawn in this repo.
Answer: yes

## PLUGIN_EVAL
```
2.1.280 (Claude Code)
Usage: claude plugin eval [options] [command] [target]
Run eval cases (<eval dir>/**/case.yaml or prompt.md + graders/*.md; the eval dir is evals/ ...)
```
Note: the `claude` shell wrapper on this Mac fails on `--version` ("profile resolution failed"), so the real binary `~/.local/share/claude/versions/2.1.280` was used.
Answer: yes

## PI_ISOLATION
`pi -p --mode json --no-session --no-tools --no-extensions --no-skills --no-context-files --no-prompt-templates --system-prompt "Reply with exactly: OK" "hi"`
```
exit=0; 17 events; files written under ~/.pi after marker: (none)
message_end usage.input = 158 tokens (no AGENTS.md or skills loaded)
```
**Gotcha:** passing `--provider google` without `--model` still ran `openai-codex/gpt-5.5`, the settings default. T6 must always pass an explicit `--model <provider/id>`.
Answer: yes

## PI_JSON_USAGE
The final `message_end` event carries usage and cost:
```
openai-codex gpt-5.5 {"input": 158, "output": 37, "reasoning": 30, "totalTokens": 195, "cost": {"input": 0.00079, "output": 0.00111, "total": 0.0019}}
```
The OpenRouter provider itself is `not_ready` on both hosts (`pi auth check --provider openrouter`), so this was measured on openai-codex.
Answer: yes

## JEV_CALL
`echo '{"original":"...לארוס...","proposed":"...להרוס..."}' | jev-ask noul "Does the proposed text fix a real spelling error in the original Hebrew sentence?"`
```
{"type": "noul", "noul": 0.61, "model": "jev-1.13.0"}   wall_ms 746
```
- Endpoint: `POST https://api.typesafe.ai/v1/systemone`, body `{state, questions: {q: {...}}, model}`, Bearer key. The response answer is at `answers.q`.
- A correct Hebrew fix scored only 0.61, below the 0.75 cascade threshold. This supports starting every Hebrew point in shadow.
Answer: yes
