# 0005. One brand file, enforced by a script

Status: accepted. Source: docs/superpowers/specs/2026-10-18-home-dashboard-margin-design.md section 5 (local,
gitignored), CLAUDE.md commands.

## Context
The site and the dashboard each carried their own colours, fonts and sizes.

## Decision
`src/brand/DESIGN.md` ("The Margin") is the only source of colours, fonts, sizes and radii.
`scripts/gen-brand-tokens.py` generates `margin.css` and the site tokens; `scripts/check-brand.py --surface all`
fails the build when a page uses a value not in the file. Two registers: site unchanged, dashboard full palette,
with light and dark tokens.

## Rejected options
- Trusting generated design output without a check: values outside the file are errors.

## Consequences
- Visual changes start in DESIGN.md, then regenerate (`--check` gates it in CI).
- Dashboard e2e baselines change only on purpose.
