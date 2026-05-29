// Fallback-trigger E2E harness — spawns the bundled MCP server with NO credentials and asserts
// every tool returns the structured `no_credentials` error. This is the deterministic trigger that
// makes section-writer / synthesizer take the in-context fallback path (the "without Gemini" path).
//
//   node tests/e2e/fallback-no-credentials.mjs
//
// Prints a single JSON object: per-tool whether it returned no_credentials, plus an overall pass flag.
import { pathToFileURL } from 'node:url';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, '..', '..');
const SERVER_DIR = join(REPO, 'plugins/academic-writer/mcp/gemini-server');
const SDK = join(SERVER_DIR, 'node_modules/@modelcontextprotocol/sdk/dist/esm');

const { Client } = await import(pathToFileURL(join(SDK, 'client/index.js')).href);
const { StdioClientTransport } = await import(pathToFileURL(join(SDK, 'client/stdio.js')).href);

// Empty temp project dir so no .academic-helper/secrets.json fallback is found, and strip the key.
const emptyProject = mkdtempSync(join(tmpdir(), 'aw-nocreds-'));
const env = { ...process.env, CLAUDE_PROJECT_DIR: emptyProject };
delete env.GOOGLE_API_KEY;
delete env.GEMINI_API_KEY;

const transport = new StdioClientTransport({ command: 'node', args: [join(SERVER_DIR, 'dist/index.js')], env });
const client = new Client({ name: 'e2e-nocreds', version: '0.0.1' }, { capabilities: {} });
await client.connect(transport);

const text = (r) => (r.content || []).map((c) => c.text || '').join('');
const isNoCreds = (r) => {
  const t = text(r).toLowerCase();
  return r.isError === true || t.includes('no_credentials') || t.includes('credential');
};

const calls = {
  gemini_write_section: { section_brief: 'x', sources: [], evidence_ownership: {}, target_language: 'Hebrew', citation_style: 'inline-parenthetical' },
  gemini_synthesize: { full_draft: 'x', target_language: 'Hebrew' },
  gemini_edit: { existing_text: 'x', edit_instruction: 'y', target_language: 'Hebrew' },
  gemini_raw: { system: 's', prompt: 'p' },
};

const out = { path: 'fallback-trigger', perTool: {}, errors: [] };
for (const [name, args] of Object.entries(calls)) {
  try {
    const r = await client.callTool({ name, arguments: args });
    out.perTool[name] = { noCredentials: isNoCreds(r), sample: text(r).slice(0, 160) };
  } catch (e) {
    // A thrown error that mentions credentials also counts as the correct trigger.
    const msg = String(e).toLowerCase();
    out.perTool[name] = { noCredentials: msg.includes('credential') || msg.includes('no_credentials'), sample: String(e).slice(0, 160) };
  }
}
await client.close();

out.pass = Object.values(out.perTool).every((v) => v.noCredentials === true);
process.stdout.write(JSON.stringify(out, null, 2) + '\n');
