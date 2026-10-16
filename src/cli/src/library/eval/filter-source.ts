/**
 * The program the locate wrapper pipes `aw library` output through (plain Node, no imports of ours). The agent must not
 * be able to tell which library answers: it gets the output with the metadata that names the library removed
 * (route, mode, shadow and backend fields, anything named after a library), library words scrubbed from metadata
 * values, and failures reduced to "lookup failed (<kind>)". Page text, titles and table-of-contents entries are the
 * book's own words and pass untouched. The real error goes to a log the run record reads, never to the agent.
 * Usage: node filter.cjs <exit code> <stdout file> <stderr file> <error log>
 */
export const FILTER_SOURCE = `
const fs = require('node:fs');
const [code, outFile, errFile, logFile] = process.argv.slice(2);
const read = (file) => { try { return fs.readFileSync(file, 'utf8'); } catch { return ''; } };
const out = read(outFile);
const err = read(errFile);
for (const file of [outFile, errFile]) { try { fs.unlinkSync(file); } catch { /* gone */ } }
const status = Number(code);
if (status !== 0) {
  try { fs.appendFileSync(logFile, JSON.stringify({ code: status, stderr: err.slice(0, 600) }) + '\\n'); } catch { /* no log */ }
  const kind = status === 2 ? 'usage' : status === 3 ? 'config' : 'failed';
  process.stderr.write('lookup failed (' + kind + ')\\n');
  process.exit(status);
}
const DROP = /^(route|mode|primary|secondary|backend|lookup_id|route_pages|shadow.*|.*route.*|.*pageindex.*|.*trove.*)$/i;
const RENAME = { trove_page: 'page' };
const CONTENT = new Set(['text', 'title', 'content', 'reason']);
const WORDS = /trove|page-?index|route|backend|shadow/gi;
function clean(value, key) {
  if (Array.isArray(value)) return value.map((item) => clean(item, key));
  if (value && typeof value === 'object') {
    const result = {};
    for (const [name, item] of Object.entries(value)) {
      if (RENAME[name]) { result[RENAME[name]] = clean(item, RENAME[name]); continue; }
      if (DROP.test(name)) continue;
      result[name] = clean(item, name);
    }
    return result;
  }
  return typeof value === 'string' && !CONTENT.has(key) ? value.replace(WORDS, 'library') : value;
}
let parsed;
try { parsed = JSON.parse(out); } catch { parsed = undefined; }
process.stdout.write(parsed === undefined ? out : JSON.stringify(clean(parsed, '')) + '\\n');
`;
