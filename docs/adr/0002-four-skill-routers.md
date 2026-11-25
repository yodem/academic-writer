# 0002. Four router skills instead of 24 listed skills

Status: accepted (shipped in 0.24.0). Source: commits c391e5e, 32038b1, 8b21d9b, 6f96394, cd54342, 4309b0a;
docs/skill-budget.md.

## Context
The plugin listed 24 skills, 9015 description characters, in every session's skill listing.

## Decision
Four listed skills, `write`, `setup`, `library`, `courses`. Each is a router: a phase word picks
`phases/<phase>.md`; a bare call runs the default phase; free text infers the phase. Old per-phase names were first
kept as one-line stubs with `metadata.moved-to`, then deleted; a test gates old command names repo-wide.

## Rejected options
- Keep 24 skills and shorten descriptions: still one listing entry per command.
- Keep the stubs: they cost listing space and kept old names alive.

## Consequences
- Listing is 4 skills, 2164 characters.
- Commands are `/academic-writer:<router> <phase>`; to add a command, add a phase.
- A 10-prompt routing eval (`evals/skill-routing/`) and `scripts/skill_budget.py` guard routing and size.
