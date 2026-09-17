// Unit-level schema-contract test for the `gemini_write_section` MCP tool.
//
//   node tests/e2e/write-section-schema-contract.mjs
//
// No network, no GOOGLE_API_KEY required. Verifies the exact call shape documented in
// src/agents/section-writer.md (structured `section_brief` object + all sibling fields)
// actually parses against the real `WriteSectionInput` Zod schema, and that the
// documented return shape parses against the real `WriteSectionOutput`
// Zod schema.
//
// Approach: the schemas live in
// plugins/academic-writer/mcp/gemini-server/src/tools/write_section.ts, which is
// TypeScript and pulls in a `.md` file via an esbuild-only `loader: { '.md': 'text' }`
// rule (see esbuild.config.mjs) — Node's built-in TypeScript support (--experimental-strip-types)
// cannot resolve that import, and the project's compiled dist/index.js bundles the whole
// server into one entry point whose top-level `main()` immediately opens a stdio MCP
// transport as a side effect of import, so it cannot be imported for its schema exports
// either. Instead this test uses the `esbuild` package (already a devDependency of
// gemini-server, installed by `npm run build:mcp`) to bundle *only*
// `src/tools/write_section.ts` in-memory (write_section.ts has no top-level side effects),
// then dynamically imports the bundled code from a temp file. This exercises the real,
// current schema — no hand-duplicated copy to drift out of sync.
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, '..', '..');
const SERVER_DIR = join(REPO, 'plugins/academic-writer/mcp/gemini-server');
const ENTRY = join(SERVER_DIR, 'src/tools/write_section.ts');

// esbuild is a devDependency of gemini-server (installed by `npm run build:mcp`), not of the
// repo root — resolve it from the server's own node_modules rather than assuming a root install.
const { build } = await import(pathToFileURL(join(SERVER_DIR, 'node_modules/esbuild/lib/main.js')).href);

let failures = 0;
function check(name, fn) {
  try {
    fn();
    console.log(`PASS  ${name}`);
  } catch (e) {
    failures += 1;
    console.log(`FAIL  ${name}`);
    console.log(`      ${e instanceof Error ? e.message : String(e)}`);
  }
}

const result = await build({
  entryPoints: [ENTRY],
  bundle: true,
  format: 'esm',
  platform: 'node',
  target: 'node20',
  write: false,
  external: ['@modelcontextprotocol/sdk', '@google/genai'],
  loader: { '.md': 'text' },
  absWorkingDir: SERVER_DIR,
});

const bundledCode = result.outputFiles[0].text;
// The bundle keeps `@modelcontextprotocol/sdk` and `@google/genai` as external bare imports
// (write_section.ts's only runtime use of them is inside `runWriteSection`, which this test
// never calls), so the temp file must live under SERVER_DIR for Node's module resolution to
// find them via SERVER_DIR/node_modules — a plain os.tmpdir() location would not resolve.
const tmpDir = mkdtempSync(join(SERVER_DIR, '.aw-schema-contract-'));
const tmpFile = join(tmpDir, 'write_section.bundled.mjs');
writeFileSync(tmpFile, bundledCode, 'utf8');

let mod;
try {
  mod = await import(pathToFileURL(tmpFile).href);
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}

const { WriteSectionInput, SelfReviewScores, SectionBrief, WriteSectionOutput } = mod;

check('WriteSectionInput is exported', () => {
  assert.ok(WriteSectionInput, 'WriteSectionInput export missing from write_section.ts');
});
check('SelfReviewScores is exported', () => {
  assert.ok(SelfReviewScores, 'SelfReviewScores export missing from write_section.ts');
});
check('SectionBrief is exported', () => {
  assert.ok(SectionBrief, 'SectionBrief export missing from write_section.ts');
});

// Exact call shape documented in src/agents/section-writer.md (Step A).
const documentedSectionBrief = {
  title: 'The Categorical Imperative in Kant',
  description: 'Introduces the categorical imperative and its role in the thesis.',
  argument_role: 'foundational-context',
  paragraph_count: 3,
  is_intro: true,
  is_conclusion: false,
  intro_or_conclusion_rules:
    'Open with "במאמר זה", state the thesis, describe the flow of the article.',
  paragraph_word_ceiling: 220,
  thesis: 'Kant grounds morality in reason alone.',
  claim: 'The categorical imperative is the formal core of that grounding.',
};

const documentedCallShape = {
  section_brief: documentedSectionBrief,
  sources: [
    {
      source_id: 'kant-1788-p42',
      author: 'קאנט',
      year: 1788,
      page: 42,
      excerpt: 'האימפרטיב הקטגורי הוא עיקרון מוסרי אוניברסלי...',
    },
  ],
  evidence_ownership: {
    'kant-1788-p42': { ownerSectionIndex: 1 },
  },
  banned_terms: [{ term: 'לצלול לעומק', reason: 'AI cliché' }],
  target_language: 'hebrew',
  prior_sections_summary: '(no prior sections)',
  citation_style: 'inline-parenthetical',
};

check('documented structured section_brief call shape parses via WriteSectionInput.safeParse', () => {
  const parsed = WriteSectionInput.safeParse(documentedCallShape);
  assert.equal(
    parsed.success,
    true,
    `safeParse failed: ${parsed.success ? '' : JSON.stringify(parsed.error.issues)}`,
  );
});

check('legacy plain-string section_brief still parses (backward compat)', () => {
  const parsed = WriteSectionInput.safeParse({
    ...documentedCallShape,
    section_brief: 'Write the introduction section.',
  });
  assert.equal(
    parsed.success,
    true,
    `safeParse failed: ${parsed.success ? '' : JSON.stringify(parsed.error.issues)}`,
  );
});

check('bare structured section_brief validates against SectionBrief schema directly', () => {
  const parsed = SectionBrief.safeParse(documentedSectionBrief);
  assert.equal(
    parsed.success,
    true,
    `safeParse failed: ${parsed.success ? '' : JSON.stringify(parsed.error.issues)}`,
  );
});

// Documented return shape (src/agents/section-writer.md, Step A): citations as
// source_id strings plus an optional `gaps` array. Self-review scores are no
// longer requested (flat maximum on 28/28 recorded calls) and must stay
// optional so an older response still parses.
check('documented return shape (citations + gaps, no scores) parses via WriteSectionOutput', () => {
  const parsed = WriteSectionOutput.safeParse({
    paragraphs: [{ text: 'פסקה.', citations: ['kant-1788-p42'], gaps: ['page number missing for kant-1788-p42'] }],
  });
  assert.equal(parsed.success, true, `safeParse failed: ${parsed.success ? '' : JSON.stringify(parsed.error.issues)}`);
});

check('a legacy response carrying self_review_scores still parses', () => {
  const parsed = WriteSectionOutput.safeParse({
    paragraphs: [{
      text: 'פסקה.',
      citations: [],
      self_review_scores: { style_fingerprint: 4, academic_language: 4, anti_ai: 42, repetition: 4 },
    }],
  });
  assert.equal(parsed.success, true, `safeParse failed: ${parsed.success ? '' : JSON.stringify(parsed.error.issues)}`);
});

console.log('');
if (failures > 0) {
  console.log(`FAIL: ${failures} assertion(s) failed.`);
  process.exit(1);
} else {
  console.log('PASS: all assertions passed.');
  process.exit(0);
}
