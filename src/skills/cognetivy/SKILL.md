---
name: cognetivy
description: Manage workflows, workflow versions, runs, step events, node results, and strict schema-backed collections in this project. Use when the user asks to start/complete a run, execute workflow nodes, log step_started/step_completed events, persist node results, or read/write structured data in collections. All operations run via the cognetivy CLI from the project root that contains .cognetivy/
---

# Cognetivy

Workflows, runs, node results, and schema-backed collections. Run commands from **project root** (directory with `.cognetivy/`). Full CLI reference: [REFERENCE.md](REFERENCE.md).

---

## When to use this skill

- User asks to start/complete a run, run the workflow, track steps, or persist ideas/sources/collections.
- User refers to "cognetivy", "workflow", "run", "collections", or ".cognetivy/".

---

## Quick start (minimal run)

**Efficient path:** `run start` → `workflow get` → `collection-schema get` (add kinds if needed) → for each node: do work → `node complete` (pipe collection JSON from stdin when possible) → `event append run_completed` + `run complete`. Use `run status --run <id>` to verify.

1. **Start a run** (from project root):
   ```bash
   cognetivy run start --input input.json --name "Short descriptive name"
   ```
   Capture `run_id` (first line) or `COGNETIVY_RUN_ID=...` (second line).

2. **Inspect workflow**: `cognetivy workflow get` - note `nodes[].id`, `input_collections`, `output_collections`.

3. **Schema**: `cognetivy collection-schema get`. Add missing kinds with `collection-schema set` so output collections exist.

4. **For each node:** Do the work, then **one call** - `node complete`:
   ```bash
   cognetivy node complete --run <run_id> --node <node_id> --status completed [--output "text" | --output-file path] [--collection-kind <kind>]
   ```
   Omit `--collection-file` to read collection payload from **stdin** (no /tmp): `echo '{"title":"x"}' | cognetivy node complete --run <run_id> --node <node_id> --status completed --collection-kind news_items`. Array = set, single object = append. Prints `COGNETIVY_NODE_RESULT_ID=...`.
   - Optional: `node start --run <run_id> --node <node_id>` first if you need `step_started` + id before doing work.
   - Avoid the legacy path (event append step_started → node-result set → collection set/append → event append step_completed) unless you cannot use `node complete`.

5. **End the run**: `echo '{"type":"run_completed","data":{}}' | cognetivy event append --run <run_id>`, then `cognetivy run complete --run <run_id>`. Use `run status --run <run_id>` to confirm.

---

## Workflow

`workflow get` (and `workflow list` / `select` / `versions` / `set --file <path>`). Versions have nodes (collection→node→collection).

## Runs

`run start` (prints `run_id`, seeds `run_input`), `run status --run <id> [--json]` (nodes + collection counts - use to verify), `run complete`, `run set-name`.

## Events

`event append --run <run_id> [--file <path>]` - omit `--file` to read from stdin. Event JSON: `type`, `data` (for step events set `data.step` = node id). E.g. `echo '{"type":"step_completed","data":{"step":"synthesize"}}' | cognetivy event append --run <run_id>`.

## Node results

Usually covered by `node complete`. For inspect or when not using it: `node-result list`, `node-result get`, `node-result set` (prints `COGNETIVY_NODE_RESULT_ID=...`).

---

## Collections (strict schema-backed)

`collection-schema get` / `set --file` (kinds + `item_schema`). `collection list --run <id>`, `collection get --run <id> --kind <kind>`. `collection set` / `collection append` need `--node` and `--node-result` (or use `node complete --collection-kind` which creates the result). Omit `--file` to read from stdin.
- **Many items:** Prefer incremental `collection append` or `node complete` per item instead of one large `collection set`. Use Markdown in long text fields for Studio.

**Payload:** Must match `item_schema` for the kind; do not include `created_at`, `created_by_node_id` - cognetivy adds them.

---

## Node runner pattern

`workflow get` once → for each node: `collection get` for that node's inputs only → do work → `node complete`. **If you can spawn sub-agents:** run each node in a separate process/agent with only that node's inputs to keep context small and avoid loading all transcripts.

## Important

- **Schema first:** `collection-schema get` before writing; add kinds if missing.
- **Step events:** `data.step` = workflow node id (for Studio).
- **Provenance:** When using `collection set`/ `append` directly (not `node complete`), create a node result first and pass `--node` + `--node-result`.
- **Always end runs:** `event append run_completed` then `run complete`.

## Performance

- **Smaller context:** Per-item extraction (e.g. per-video) over all-at-once when a node maps over a list.
- **Parallel sub-agents:** For data-parallel nodes (e.g. 10 transcripts), spawning one agent per item in parallel can yield ~10x wall-clock speedup - highest-leverage for map-over-list workflows.
- **Structured output:** Future extensions may enforce "output must match this schema" so the agent skips manual schema-checking.
