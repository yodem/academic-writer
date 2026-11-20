# Skill listing budget

How much of the model's skill listing Academic Writer uses, measured with
`python3 scripts/skill_budget.py measure plugins/academic-writer/skills`
(`/doctor` shows the same listing cost in a live session).

| | Listed skills | Listed description characters |
|---|---|---|
| Before (0.23.1, `tests/fixtures/skill_budget_baseline.json`) | 24 | 9015 |
| After (0.24.0) | 4 | 2164 |

The four listed skills are `write`, `setup`, `library` and `courses`. No forwarding stubs remain.

## Routing eval

`evals/skill-routing/prompts.json` holds 10 prompts, each with the router skill and phase it should select. Target: 9 of 10 select the expected skill. Run each prompt in a fresh headless session and compare the skill and phase file read (`scripts/skill_budget.py reads`).
