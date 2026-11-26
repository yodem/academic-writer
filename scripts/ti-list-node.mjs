// Lists node:test tests of src/cli as jsonl on stdout (run from src/cli): builds dist-test with build-tests.mjs,
// then loads every bundle under scripts/ti-node-recorder.mjs (no test body runs). Ids are
// `<path relative to the repo root>::<describe > test chain>`, using the source test file when the
// bundle's name maps to one (tests/, ../hooks/src/**, ../mod/), else the bundle path.
import { spawnSync } from 'node:child_process';
import { readdirSync, readFileSync, mkdtempSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname, basename, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const cwd = process.cwd();
const root = resolve(cwd, '../..');
const build = spawnSync(process.execPath, ['build-tests.mjs'], { cwd, stdio: ['ignore', 2, 2] });
if (build.status !== 0) { console.error('build-tests.mjs failed'); process.exit(1); }

const walk = (d) => (existsSync(d) ? readdirSync(d, { withFileTypes: true }).flatMap((e) =>
  e.isDirectory() ? (e.name === 'node_modules' ? [] : walk(join(d, e.name))) : [join(d, e.name)]) : []);
const sources = new Map();
for (const dir of ['tests', '../hooks/src', '../mod']) {
  for (const f of walk(resolve(cwd, dir))) {
    const m = basename(f).match(/^(.*\.test)\.(ts|mts|js|mjs)$/);
    if (m && !sources.has(m[1])) sources.set(m[1], f);
  }
}

const bundles = walk(resolve(cwd, 'dist-test')).filter((f) => f.endsWith('.test.mjs')).sort();
const tmp = mkdtempSync(join(tmpdir(), 'ti-node-'));
const seen = new Map();
let rc = 0;
for (const b of bundles) {
  const out = join(tmp, 'out.jsonl');
  const p = spawnSync(process.execPath, ['--import', join(here, 'ti-node-recorder.mjs'), b],
    { cwd, env: { ...process.env, TI_OUT: out }, stdio: ['ignore', 'ignore', 2], timeout: 120000 });
  if (p.status !== 0) { console.error(`recorder failed for ${b}: exit ${p.status} ${p.error || ''}`); rc = 1; continue; }
  const src = sources.get(basename(b).replace(/\.mjs$/, '')) || b;
  const rel = relative(root, src).split(sep).join('/');
  const text = existsSync(out) ? readFileSync(out, 'utf8') : '';
  rmSync(out, { force: true });
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    const r = JSON.parse(line);
    let id = `${rel}::${r.id}`;
    const n = (seen.get(id) || 0) + 1; seen.set(id, n);
    if (n > 1) id += ` #${n}`;
    process.stdout.write(JSON.stringify({ id, skipped: r.skipped }) + '\n');
  }
}
rmSync(tmp, { recursive: true, force: true });
process.exit(rc);
