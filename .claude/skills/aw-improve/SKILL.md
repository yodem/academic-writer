---
name: aw-improve
description: "Review academic-writer feedback ledgers and turn recurring defects into eval cases and development goals. Use when improving or triaging academic-writer plugin defects."
user-invocable: true
allowed-tools: [Bash, Read, Write, Glob]
metadata: {author: "Yotam Fromm", version: "0.12.0"}
---

# Improve academic-writer

Run `scripts/aw-improve-report.py --ledger '<plugin data>/feedback/ledger.jsonl' --runs '.academic-helper/runs/*/feedback/ledger.jsonl' --json`. Review clusters with at least two examples. For each, create a reproducing eval case under `evals/<cluster-slug>/` and draft a `/work` goal with the failing behavior and expected result.

Close a cluster only after its eval fails before the fix and passes after it. For Jev evaluation, use `--jev` and include the point's label file under `--runs`; promote only on the configured roster bar.
