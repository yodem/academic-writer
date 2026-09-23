# Install migration: 10 per-project installs → one user-scope install (T4)

**Status: waiting for the author's approval. Nothing below has been run.**

Why: fixes shipped in releases never reached real use, because the plugin is installed 10 times at 4 versions (0.5.0, 0.7.1, 0.10.0, 0.10.1). One user-scope install updates everywhere at once. Hooks already skip any project without `.academic-helper/profile.md`, so installing user-wide changes nothing in other projects. The voice store (`${CLAUDE_PLUGIN_DATA}`) is shared by every scope, so `--keep-data` preserves it.

## Current installs (from `~/.claude/plugins/installed_plugins.json`, 2026-09-23)

| # | Scope | Project | Version | Dir exists |
|---|---|---|---|---|
| 1 | project | `~/dev/Academic Helper` | 0.10.0 | **no** (stale entry) |
| 2 | local | `~/dev/bar-ilan/ester` | 0.10.0 | **no** (stale entry) |
| 3 | project | `~/dev/jewish-studies/bar-ilan/ester` | 0.7.1 | yes |
| 4 | project | `~/dev/jewish-studies/bar-ilan/shalom` | 0.7.1 | yes |
| 5 | local | `~/dev/bar-ilan/mikdashim` | 0.5.0 | **no** (stale entry) |
| 6 | local | `~/dev/jewish-studies/bar-ilan/shalom-blogs` | 0.7.1 | yes |
| 7 | local | `~/dev/jewish-studies/bar-ilan/myer-joel-wigoder` | 0.7.1 | yes |
| 8 | local | `~/dev/jewish-studies/bar-ilan/20th-century` | 0.7.1 | yes |
| 9 | local | `~/dev/jewish-studies/bar-ilan/shmaria` | 0.10.0 | yes |
| 10 | project | `~/dev/jewish-studies/bar-ilan/kabalah` | 0.10.1 | yes |

## Commands (run after approval, in this order)

1. Install once at user scope:
```bash
claude plugin install academic-writer@academic-writer --scope user
```
2. For each row above whose directory exists, remove the per-project install and keep the data:
```bash
cd <project> && claude plugin uninstall academic-writer@academic-writer --scope <scope> --keep-data
```
   Rows whose directory no longer exists are stale registry entries. Remove them with the same command run from any directory, adding `--scope <scope>`. If the CLI refuses because the path is missing, leave the entry and record that here.
3. Verify: `claude plugin list` shows one academic-writer install at user scope. `/academic-writer:health` in the kabalah project reports version 0.11.0.

## Record

(filled in after execution: command outputs and the final `claude plugin list`)
