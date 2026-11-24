# 0004. A researcher-chosen home folder and a local stdlib dashboard

Status: accepted. Source: docs/superpowers/specs/2026-10-18-home-dashboard-margin-design.md (local, gitignored),
CLAUDE.md conventions.

## Context
Course data lived under the plugin's own folder; students and lecturers needed one visible place, a dashboard and
per-workspace overrides.

## Decision
One home folder chosen at setup holds `home.md`, `workspaces.json` and the term registry. A workspace profile stores
only overrides, merged over home at read time (home values, then overrides). The dashboard is a Python stdlib
server on 127.0.0.1 with a per-run key and cookie, Host/Origin checks and SSE. "No global pollution" gains this one
named exception. Migration is an explicit, previewed, backed-up command that deletes nothing.

## Rejected options
- A separate Projects page: the Writing page lists every workspace.
- A browser-chosen home: the setup skill asks, so Cowork sandboxes work.

## Consequences
- Hooks and tools continue with workspace overrides if home is unreachable and print one plain line.
- The nightly job is macOS only; other systems get home, workspaces and dashboard.
