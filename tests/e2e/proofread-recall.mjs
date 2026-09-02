// proofread-recall.mjs — MANUAL eval harness for the hebrew-recall regression fixture.
//
// THIS IS NOT A CI TEST. It is intentionally excluded from `python3 -m pytest tests/`
// and from any npm script that gates a release. It calls real Claude models (via the
// `claude` CLI, headless mode) to run the mechanical (proofreader) and editorial
// (editor) finder stages over tests/fixtures/proofread/hebrew-recall/excerpt.md, then
// scores the model's own output against the fixed expectations in
// expected-mechanical.json and expected-editorial.json.
//
// Why manual, not deterministic: a model call is not reproducible run-to-run (the
// same prompt can find nine of nine finds on one run and eight of nine on the next),
// costs tokens/time, and needs the `claude` CLI plus a working auth/session on the
// machine that runs it. None of that belongs in a fast, hermetic pytest suite —
// tests/test_proofread_fixture.py covers everything about this fixture that CAN be
// asserted deterministically (file shape, JSON validity, that the nine `before`
// strings actually occur in excerpt.md, that finder is 'mechanical-llm' on every
// entry, that the control paragraphs are clean, that this script itself is valid
// JS). This script covers the one thing that cannot be asserted deterministically:
// whether the actual model, today, on this fixture, still finds what the 2026-07-10
// pass missed.
//
// Scope of this harness vs. the full pipeline (src/workflows/proofread.js): the real
// workflow is a Dynamic-Workflow script that only runs inside Claude Code's Workflow
// tool (agent()/pipeline()/log() are runtime-injected globals; it has no filesystem
// access and cannot be invoked by plain `node`). This harness instead calls the same
// two agent prompts (src/agents/proofreader.md, src/agents/editor.md) directly via the
// `claude` CLI's headless print mode against the fixture's single, small excerpt (it
// does not need chunking, multi-round convergence, or refute-verify — the fixture is
// one chunk of test prose). It is a faithful single-pass check of finder RECALL, not
// a rehearsal of the full multi-stage workflow; running the real
// `/academic-writer:proofread --venue <slug>` skill against this fixture inside an
// actual Claude Code session is the complementary, closer-to-production check.
//
// Usage:
//   node tests/e2e/proofread-recall.mjs
//
// Requires the `claude` CLI on PATH, authenticated, with network access. If it is
// missing or a call fails, this script reports that clearly per finding/category
// (as a miss, not a crash) so a partial run still prints a usable table.
//
// `claude -p <prompt> --output-format json` does NOT return the model's raw text on
// stdout — it returns a JSON ENVELOPE describing the run (observed top-level fields:
// type, subtype, is_error, session_id, result, usage, ...), and the model's actual
// reply text lives inside the string field `result`. `unwrapEnvelope()` below extracts
// that field when stdout looks like this envelope, and falls back to treating stdout
// as already-raw text otherwise (e.g. under PROOFREAD_RECALL_FAKE_RESPONSE, see below,
// or if a future CLI version changes its output shape).
//
// Three distinct outcomes are reported per stage, deliberately not collapsed into one
// number: (1) a VALID RUN with a well-formed changes array and some hits/misses; (2) a
// VALID RUN whose changes array is well-formed but empty — a real, meaningful 0/N; and
// (3) an INVALID RUN, where the response could not be parsed into a changes object at
// all (CLI failure, unparseable text, or JSON with no `changes` array anywhere in it).
// Only case (3) is not a measurement: it prints a loud block naming the failure and the
// process exits NON-ZERO so an invalid run's zero can never be silently recorded as a
// real one. Cases (1) and (2) exit zero.
//
// TEST-ONLY: if the environment variable PROOFREAD_RECALL_FAKE_RESPONSE is set to a
// file path, that file's contents are used in place of every `claude` CLI call (for
// both the mechanical and editorial stages), so tests/test_eval_harness_scoring.py can
// exercise the envelope-unwrapping / JSON-extraction / hit-counting / valid-vs-invalid
// classification logic deterministically, with no model call, no tokens, and no
// dependency on the `claude` CLI being installed or authenticated. Never set this
// outside tests — it bypasses the real model call entirely.
//
// Ship gate (plan of record, Phase 1.6): 9/9 mechanical, 5/5 editorial.
// Record the numbers this script prints in docs/proofread-feature.md when re-run.

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, '..', '..');
const FIXTURE_DIR = join(REPO, 'tests', 'fixtures', 'proofread', 'hebrew-recall');

// TEST-ONLY escape hatch — see header comment above.
const FAKE_RESPONSE_PATH = process.env.PROOFREAD_RECALL_FAKE_RESPONSE || null;

function nfc(s) {
  return s.normalize('NFC');
}

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

function loadAgentPrompt(agentName) {
  const raw = readFileSync(join(REPO, 'src', 'agents', `${agentName}.md`), 'utf8');
  // Strip the YAML frontmatter block; the harness only needs the prompt body.
  return raw.replace(/^---\n[\s\S]*?\n---\n/, '');
}

// Calls `claude -p <prompt> --output-format json` and returns the raw stdout (the
// JSON envelope, see unwrapEnvelope below), or null (never throws) so one failed call
// cannot abort the whole harness run. Under PROOFREAD_RECALL_FAKE_RESPONSE (test-only)
// it instead returns the contents of that file, unchanged.
function callClaudeHeadless(prompt) {
  if (FAKE_RESPONSE_PATH) {
    try {
      return readFileSync(FAKE_RESPONSE_PATH, 'utf8');
    } catch (err) {
      console.error(`  [PROOFREAD_RECALL_FAKE_RESPONSE read error] ${err.message}`);
      return null;
    }
  }
  const result = spawnSync('claude', ['-p', prompt, '--output-format', 'json'], {
    encoding: 'utf8',
    maxBuffer: 1024 * 1024 * 32,
    timeout: 5 * 60 * 1000,
  });
  if (result.error) {
    console.error(`  [claude CLI error] ${result.error.message}`);
    return null;
  }
  if (result.status !== 0) {
    console.error(`  [claude CLI exit ${result.status}] ${(result.stderr || '').slice(0, 400)}`);
    return null;
  }
  return result.stdout;
}

// `claude -p ... --output-format json` wraps the model's actual reply text inside a
// top-level string field named `result` (observed shape: {type:"result",
// subtype:"success", is_error:false, session_id, result:"<model text>", usage, ...}).
// Extracts that field when stdout looks like this envelope; otherwise treats stdout as
// already being the raw model text (so the harness also works when fed raw text
// directly, as under PROOFREAD_RECALL_FAKE_RESPONSE, or if a future CLI version emits
// plain text). Never throws.
function unwrapEnvelope(stdout) {
  if (!stdout) return { text: stdout, envelope: null };
  let parsed;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    return { text: stdout, envelope: null };
  }
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) &&
      typeof parsed.result === 'string' && 'type' in parsed) {
    return { text: parsed.result, envelope: parsed };
  }
  // Parsed as JSON but doesn't look like the envelope -- most likely stdout was
  // already the raw (unwrapped) JSON the model returned. Hand the original stdout to
  // extractJson unchanged so its own fence/brace-scanning logic still applies.
  return { text: stdout, envelope: null };
}

// Best-effort extraction of a JSON object/array from a model response that may wrap
// it in prose or a ```json fence.
function extractJson(text) {
  if (!text) return null;
  const fenced = text.match(/```json\s*\n([\s\S]*?)\n```/);
  const candidate = fenced ? fenced[1] : text;
  try {
    return JSON.parse(candidate);
  } catch {
    // Fall back to the widest {...} span.
    const start = candidate.indexOf('{');
    const end = candidate.lastIndexOf('}');
    if (start >= 0 && end > start) {
      try {
        return JSON.parse(candidate.slice(start, end + 1));
      } catch {
        return null;
      }
    }
    return null;
  }
}

// Recursively searches for a property literally named `changes` whose value is an
// array, anywhere in the parsed tree (top level, or nested under a wrapper key models
// are not always consistent about). Returns the array (possibly empty -- an empty
// array is a legitimate found value, since `Array.isArray([])` and `[]` is truthy in
// JS) or undefined if no such property exists anywhere.
function findChangesArray(node) {
  if (Array.isArray(node)) {
    for (const item of node) {
      const found = findChangesArray(item);
      if (found !== undefined) return found;
    }
    return undefined;
  }
  if (node && typeof node === 'object') {
    if (Array.isArray(node.changes)) return node.changes;
    for (const value of Object.values(node)) {
      const found = findChangesArray(value);
      if (found !== undefined) return found;
    }
  }
  return undefined;
}

// Classifies one stage's raw CLI/fake output into exactly one of three outcomes:
//   'invalid'    - not a measurement at all (no output, is_error, unparseable JSON, or
//                  parsed JSON with no `changes` array anywhere in it).
//   'valid-zero' - a well-formed changes array that is genuinely empty (a real 0/N).
//   'valid'      - a well-formed, non-empty changes array (score by hit/miss below).
// Never throws.
function classifyResponse(rawStdout, stageLabel) {
  if (!rawStdout) {
    return {
      status: 'invalid',
      stageLabel,
      reason: 'no output from claude CLI (see [claude CLI ...] error line above)',
      snippet: '',
    };
  }
  const { text, envelope } = unwrapEnvelope(rawStdout);
  if (envelope && envelope.is_error) {
    return {
      status: 'invalid',
      stageLabel,
      reason: 'claude CLI envelope reported is_error: true',
      snippet: String(text ?? rawStdout).slice(0, 300),
    };
  }
  const parsed = extractJson(text);
  if (parsed === null) {
    return {
      status: 'invalid',
      stageLabel,
      reason: 'response could not be parsed as JSON (no valid object/array found)',
      snippet: String(text).slice(0, 300),
    };
  }
  const changes = findChangesArray(parsed);
  if (changes === undefined) {
    return {
      status: 'invalid',
      stageLabel,
      reason: "parsed valid JSON, but no 'changes' array was found anywhere in it",
      snippet: JSON.stringify(parsed).slice(0, 300),
    };
  }
  return {
    status: changes.length === 0 ? 'valid-zero' : 'valid',
    stageLabel,
    parsed,
    changes,
  };
}

function printInvalidBlock(classification) {
  console.log('');
  console.log(`  !!! INVALID RUN — ${classification.stageLabel} stage is NOT a measurement !!!`);
  console.log(`      Reason: ${classification.reason}`);
  console.log(`      First ~300 chars actually received: ${JSON.stringify(classification.snippet)}`);
  console.log('');
}

function collectChangeBeforeStrings(parsed) {
  // Accept either a bare changes-schema object ({stage, changes:[...]}) or a wrapper
  // object holding one under a 'result'/'changes' key — models are not perfectly
  // consistent about the outer shape even when the prompt asks for one.
  const out = [];
  const visit = (node) => {
    if (Array.isArray(node)) {
      node.forEach(visit);
    } else if (node && typeof node === 'object') {
      if (typeof node.before === 'string') out.push(node.before);
      Object.values(node).forEach(visit);
    }
  };
  visit(parsed);
  return out.map(nfc);
}

async function main() {
  const excerpt = nfc(readFileSync(join(FIXTURE_DIR, 'excerpt.md'), 'utf8'));
  const expectedMechanical = readJson(join(FIXTURE_DIR, 'expected-mechanical.json'));
  const expectedEditorial = readJson(join(FIXTURE_DIR, 'expected-editorial.json'));
  const venue = readFileSync(join(FIXTURE_DIR, 'venue-example.md'), 'utf8');

  console.log('=== proofread-recall (manual eval, not CI) ===');
  console.log(`Fixture: ${FIXTURE_DIR}`);
  if (FAKE_RESPONSE_PATH) {
    console.log(`(TEST MODE: using PROOFREAD_RECALL_FAKE_RESPONSE=${FAKE_RESPONSE_PATH} instead of the claude CLI)`);
  }
  console.log('');

  let anyInvalid = false;

  // --- Mechanical stage ----------------------------------------------------
  console.log('--- Mechanical finder (proofreader) ---');
  const proofreaderPrompt = loadAgentPrompt('proofreader');
  const mechanicalPrompt = [
    proofreaderPrompt,
    '',
    '## Chunk to review',
    '',
    'Below is the single chunk (the whole fixture). Return ONLY a JSON object matching',
    'changes-schema.json ({"stage":"mechanical","changes":[...]})  no prose, no markdown fence.',
    '',
    excerpt,
  ].join('\n');

  const mechanicalRaw = callClaudeHeadless(mechanicalPrompt);
  const mechanicalClassification = classifyResponse(mechanicalRaw, 'Mechanical');

  const mechanicalTotal = expectedMechanical.errors.length;
  let mechanicalHits = 0;

  if (mechanicalClassification.status === 'invalid') {
    anyInvalid = true;
    printInvalidBlock(mechanicalClassification);
    for (const err of expectedMechanical.errors) {
      console.log(`  [ N/A ] ${err.id}  before="${err.before}"  (run invalid, cannot score)`);
    }
  } else {
    const foundBeforeStrings = collectChangeBeforeStrings(mechanicalClassification.parsed);
    for (const err of expectedMechanical.errors) {
      const needle = nfc(err.before);
      const hit = foundBeforeStrings.some((f) => f.includes(needle) || needle.includes(f));
      if (hit) mechanicalHits += 1;
      console.log(`  [${hit ? 'HIT ' : 'MISS'}] ${err.id}  before="${err.before}"`);
    }
    if (mechanicalClassification.status === 'valid-zero') {
      console.log('  (VALID RUN — well-formed, empty changes array: this 0 is a real measurement.)');
    }
  }
  console.log(`Mechanical recall: ${mechanicalHits}/${mechanicalTotal}`);
  console.log('');

  // --- Editorial stage -------------------------------------------------------
  console.log('--- Editorial finder (editor) ---');
  const editorPrompt = loadAgentPrompt('editor');
  const editorialPrompt = [
    editorPrompt,
    '',
    '## Venue profile',
    '',
    venue,
    '',
    '## Article to review',
    '',
    'Return ONLY a JSON object matching changes-schema.json',
    '({"stage":"editorial","changes":[...]}), no prose, no markdown fence.',
    '',
    excerpt,
  ].join('\n');

  const editorialRaw = callClaudeHeadless(editorialPrompt);
  const editorialClassification = classifyResponse(editorialRaw, 'Editorial');

  const editorialTotal = expectedEditorial.categories.length;
  let editorialHits = 0;

  if (editorialClassification.status === 'invalid') {
    anyInvalid = true;
    printInvalidBlock(editorialClassification);
    for (const cat of expectedEditorial.categories) {
      console.log(`  [ N/A ] ${cat.id}  category="${cat.category}" (plan label: ${cat.planLabel})  (run invalid, cannot score)`);
    }
  } else {
    const editorialFindings = [];
    const visit = (node) => {
      if (Array.isArray(node)) node.forEach(visit);
      else if (node && typeof node === 'object') {
        if (typeof node.type === 'string' || typeof node.category === 'string') {
          editorialFindings.push(node);
        }
        Object.values(node).forEach(visit);
      }
    };
    visit(editorialClassification.parsed);

    for (const cat of expectedEditorial.categories) {
      const wantType = cat.category;
      const hit = editorialFindings.some((f) => {
        const t = f.type || f.category;
        if (t !== wantType) return false;
        const snippetWords = cat.snippet.split(/\s+/).slice(0, 4).join(' ');
        const haystack = [f.snippet, f.before, f.rationale, f.note].filter(Boolean).join(' ');
        return haystack.includes(snippetWords) || Math.abs((f.line || -1) - cat.line) <= 2;
      });
      if (hit) editorialHits += 1;
      console.log(`  [${hit ? 'HIT ' : 'MISS'}] ${cat.id}  category="${cat.category}" (plan label: ${cat.planLabel})`);
    }
    if (editorialClassification.status === 'valid-zero') {
      console.log('  (VALID RUN — well-formed, empty changes array: this 0 is a real measurement.)');
    }
  }
  console.log(`Editorial category recall: ${editorialHits}/${editorialTotal}`);
  console.log('');

  console.log('=== Summary ===');
  console.log(`Mechanical: ${mechanicalHits}/${mechanicalTotal}`);
  console.log(`Editorial:  ${editorialHits}/${editorialTotal}`);
  console.log('Ship gate (plan Phase 1.6): 9/9 mechanical, 5/5 editorial.');

  if (anyInvalid) {
    console.log('');
    console.log('NOTE: at least one stage above was an INVALID RUN, not a real measurement --');
    console.log('see the "!!! INVALID RUN !!!" block(s) for which stage and why. Do NOT record');
    console.log('the numbers above in docs/proofread-feature.md; re-run with a working `claude`');
    console.log('CLI session first.');
    process.exitCode = 1;
  }
}

await main();
