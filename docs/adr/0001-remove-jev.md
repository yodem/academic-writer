# 0001. Remove Jev from the plugin

Status: accepted (shipped in 0.23.0). Source: CHANGELOG 0.23.0, commit a750135.

## Context
Jev was an optional experimental decision-scoring service: `aw decide`, a `decide()` cascade at 10 decision points
and a proofread shadow scorer, all in shadow mode (it only logged answers). It needed its own API key and sent
data to an outside service.

## Decision
Remove `aw decide`, every shadow log of a Jev answer, the `jev_api_key` setting, the env export and the thresholds.

## Rejected options
- Keep it in shadow mode until 100 labelled examples exist (the earlier plan): it never changed a result.

## Consequences
- Drafting, evidence, proofreading, synthesis and revision behave as before.
- Nothing is sent to that service; one fewer key in setup.
- A decision gate that needs a model stays the auditor, never a scoring service.
