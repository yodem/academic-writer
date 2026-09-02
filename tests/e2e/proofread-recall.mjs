// proofread-recall.mjs — MANUAL eval harness for the katharsis regression fixture.
//
// THIS IS NOT A CI TEST. It is intentionally excluded from `python3 -m pytest tests/`
// and from any npm script that gates a release. It calls real Claude models (via the
// `claude` CLI, headless mode) to run the mechanical (proofreader) and editorial
// (editor) finder stages over tests/fixtures/proofread/katharsis/excerpt.md, then
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
// `/academic-writer:proofread --venue katharsis` skill against this fixture inside an
// actual Claude Code session is the complementary, closer-to-production check.
//
// Usage:
//   node tests/e2e/proofread-recall.mjs
//
// Requires the `claude` CLI on PATH, authenticated, with network access. If it is
// missing or a call fails, this script reports that clearly per finding/category
// (as a miss, not a crash) so a partial run still prints a usable table.
//
// Ship gate (plan of record, Phase 1.6): 9/9 mechanical, 5/5 editorial categories.
// Record the numbers this script prints in docs/proofread-feature.md when re-run.

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, '..', '..');
const FIXTURE_DIR = join(REPO, 'tests', 'fixtures', 'proofread', 'katharsis');

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

// Calls `claude -p <prompt> --output-format json` and returns the raw text result, or
// null (never throws) so one failed call cannot abort the whole harness run.
function callClaudeHeadless(prompt) {
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
  const venue = readFileSync(join(FIXTURE_DIR, 'venue.md'), 'utf8');

  console.log('=== proofread-recall (manual eval, not CI) ===');
  console.log(`Fixture: ${FIXTURE_DIR}`);
  console.log('');

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
  const mechanicalParsed = extractJson(mechanicalRaw);
  const foundBeforeStrings = mechanicalParsed ? collectChangeBeforeStrings(mechanicalParsed) : [];

  let mechanicalHits = 0;
  for (const err of expectedMechanical.errors) {
    const needle = nfc(err.before);
    const hit = foundBeforeStrings.some((f) => f.includes(needle) || needle.includes(f));
    if (hit) mechanicalHits += 1;
    console.log(`  [${hit ? 'HIT ' : 'MISS'}] ${err.id}  before="${err.before}"`);
  }
  const mechanicalTotal = expectedMechanical.errors.length;
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
  const editorialParsed = extractJson(editorialRaw);
  const editorialFindings = [];
  if (editorialParsed) {
    const visit = (node) => {
      if (Array.isArray(node)) node.forEach(visit);
      else if (node && typeof node === 'object') {
        if (typeof node.type === 'string' || typeof node.category === 'string') {
          editorialFindings.push(node);
        }
        Object.values(node).forEach(visit);
      }
    };
    visit(editorialParsed);
  }

  let editorialHits = 0;
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
  const editorialTotal = expectedEditorial.categories.length;
  console.log(`Editorial category recall: ${editorialHits}/${editorialTotal}`);
  console.log('');

  console.log('=== Summary ===');
  console.log(`Mechanical: ${mechanicalHits}/${mechanicalTotal}`);
  console.log(`Editorial:  ${editorialHits}/${editorialTotal}`);
  console.log('Ship gate (plan Phase 1.6): 9/9 mechanical, 5/5 editorial.');
  if (!mechanicalRaw || !editorialRaw) {
    console.log('');
    console.log('NOTE: one or both `claude` CLI calls did not return output (see errors above).');
    console.log('This run is NOT a valid recall measurement — re-run with a working `claude` CLI');
    console.log('session before recording numbers in docs/proofread-feature.md.');
  }
}

await main();
