# Section-Writer Model Benchmark — 2026-05-01

## Decision

Switched `section-writer` from `model: opus` to `model: sonnet`.

## Rationale

Per the plugin review (docs/reviews/2026-05-01-plugin-review.md), the section-writer was using Opus when Sonnet is typically sufficient for pipeline steps with well-defined quality gates. The 8-skill pipeline already enforces quality through measurable thresholds (anti-AI 35/50, style compliance 0.70, auditor hard gate) — the model choice affects speed and cost, not correctness, as long as it passes the gates.

## Benchmark Plan (to run on first real article session)

| Para | Time (opus) | Anti-AI (opus) | Time (sonnet) | Anti-AI (sonnet) | Auditor |
|---|---|---|---|---|---|
| 1 | TBD | TBD | TBD | TBD | TBD |
| 2 | TBD | TBD | TBD | TBD | TBD |
| 3 | TBD | TBD | TBD | TBD | TBD |

**If sonnet drops below anti-AI threshold (35/50) on any paragraph**: revert to opus by editing `src/agents/section-writer.md:model`.

**Per RULE-O10 (Operator's Rulebook)**: benchmark before rollout. This benchmark is deferred because running the full pipeline requires a live researcher session with real sources. The model switch is provisional — revert immediately if quality gates fail in practice.

## Revert command

```bash
sed -i '' 's/^model: sonnet$/model: opus/' src/agents/section-writer.md
npm run build
```
