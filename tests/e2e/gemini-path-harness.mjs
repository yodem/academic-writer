// Gemini-path E2E harness — spawns the freshly-built bundled MCP server and exercises the
// real Gemini integration end-to-end against the Hebrew fixture project. Requires GOOGLE_API_KEY.
//
//   node tests/e2e/gemini-path-harness.mjs
//
// Prints a single JSON object on stdout with the real Hebrew outputs + pass flags so a caller
// (or the finalize workflow) can verify the Gemini path produces cited Hebrew prose.
import { pathToFileURL } from 'node:url';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, '..', '..');
const SERVER_DIR = join(REPO, 'plugins/academic-writer/mcp/gemini-server');
const SDK = join(SERVER_DIR, 'node_modules/@modelcontextprotocol/sdk/dist/esm');

const { Client } = await import(pathToFileURL(join(SDK, 'client/index.js')).href);
const { StdioClientTransport } = await import(pathToFileURL(join(SDK, 'client/stdio.js')).href);

const fixtureDir = join(REPO, 'tests/e2e/fixture-project');
const sources = JSON.parse(readFileSync(join(fixtureDir, '.academic-helper/sources.json'), 'utf8'));
const excerpts = sources.flatMap((s) =>
  (s.passages || []).map((p) => ({ source_id: s.sourceId, author: s.author, year: s.year, page: p.page, excerpt: p.text })),
);

const transport = new StdioClientTransport({
  command: 'node',
  args: [join(SERVER_DIR, 'dist/index.js')],
  env: { ...process.env },
});
const client = new Client({ name: 'e2e-gemini', version: '0.0.1' }, { capabilities: {} });
await client.connect(transport);

const text = (r) => (r.content || []).map((c) => c.text || '').join('');
const out = { path: 'gemini', tools: {}, samples: {}, errors: [] };

try {
  const toolList = await client.listTools();
  out.tools.registered = toolList.tools.map((t) => t.name);

  // 1. write_section — flagship
  const ws = await client.callTool({
    name: 'gemini_write_section',
    arguments: {
      section_brief:
        'מבוא למאמר: הצג את אפוריית הזמן של אוגוסטינוס ונסח את התזה בכ-90 מילים. שלב ציטוט אחד מן המקור.',
      sources: excerpts,
      evidence_ownership: {},
      target_language: 'Hebrew',
      citation_style: 'inline-parenthetical',
    },
  });
  const wsObj = JSON.parse(text(ws));
  out.tools.write_section = !ws.isError && Array.isArray(wsObj.paragraphs) && wsObj.paragraphs.length > 0;
  out.samples.write_section = { text: wsObj.paragraphs?.[0]?.text ?? '', citations: wsObj.paragraphs?.[0]?.citations ?? [] };

  // 2. synthesize — surgical coherence pass over the produced paragraph
  const syn = await client.callTool({
    name: 'gemini_synthesize',
    arguments: {
      full_draft: wsObj.paragraphs.map((p) => p.text).join('\n\n'),
      target_language: 'Hebrew',
    },
  }).catch((e) => ({ isError: true, content: [{ text: String(e) }] }));
  out.tools.synthesize = !syn.isError;
  out.samples.synthesize = text(syn).slice(0, 400);

  // 3. edit — tone tweak on a sentence
  const ed = await client.callTool({
    name: 'gemini_edit',
    arguments: {
      existing_text: out.samples.write_section.text,
      edit_instruction: 'הפוך את המשפט הראשון לחד וישיר יותר, מבלי לשנות את הציטוט.',
      target_language: 'Hebrew',
    },
  }).catch((e) => ({ isError: true, content: [{ text: String(e) }] }));
  out.tools.edit = !ed.isError;
  out.samples.edit = text(ed).slice(0, 400);

  // 4. raw low-cap edge note (documents the known dynamic-thinking edge; NOT used by any skill)
  const rawLow = await client.callTool({
    name: 'gemini_raw',
    arguments: { system: 'ענה בעברית במילה אחת.', prompt: 'אמור: שלום', max_output_tokens: 256 },
  }).catch((e) => ({ isError: true, content: [{ text: String(e) }] }));
  let rawLowText = '';
  try { rawLowText = JSON.parse(text(rawLow)).text ?? ''; } catch { rawLowText = text(rawLow); }
  out.tools.raw_lowcap_nonempty = rawLowText.trim().length > 0;
  out.samples.raw_lowcap = rawLowText.slice(0, 120);
} catch (e) {
  out.errors.push(String(e));
} finally {
  await client.close();
}

out.pass = out.tools.write_section === true && out.tools.synthesize === true && out.tools.edit === true;
process.stdout.write(JSON.stringify(out, null, 2) + '\n');
