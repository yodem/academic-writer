// test-integrity: `node --import ti-node-recorder.mjs <bundled-test-file>` loads a node:test file WITHOUT running
// any test. A resolve hook swaps `node:test` for this module's recorder exports; describe callbacks run (so
// nested tests are collected), test bodies and hooks never do. At exit the describe>test chain of every test is
// appended to $TI_OUT as jsonl {"id": "<chain>", "skipped": bool}; skip and todo (options or .skip/.todo) give skipped=true.
// A test.skip() call inside a body cannot be seen. Async describe callbacks are not awaited.
import { register } from 'node:module';
import { appendFileSync } from 'node:fs';

const self = import.meta.url;

if (!globalThis.__ti_recorder) {
  globalThis.__ti_recorder = { rows: [], stack: [] };
  register('data:text/javascript,' + encodeURIComponent(
    `export async function resolve(s, c, n) { if (s === 'node:test') return { url: ${JSON.stringify(self + '?recorder')}, shortCircuit: true }; return n(s, c); }`));
  process.on('exit', () => {
    if (process.env.TI_OUT) appendFileSync(process.env.TI_OUT, globalThis.__ti_recorder.rows.map((r) => JSON.stringify(r) + '\n').join(''));
  });
}

// ---- the replacement for node:test (this same file, loaded under the ?recorder URL)
const R = globalThis.__ti_recorder;
const noop = () => {};

function parse(name, a, b) {
  if (typeof name === 'function') return { name: name.name || '<anonymous>', opts: {}, fn: name };
  let opts = {}, fn;
  if (typeof a === 'function') fn = a;
  else { opts = a || {}; fn = b; }
  return { name: String(name), opts, fn };
}
const flagged = (o, k) => Boolean(o && o[k]);

function record(kind, mode, name, a, b) {
  const { name: n, opts, fn } = parse(name, a, b);
  const skipped = mode === 'skip' || mode === 'todo' || flagged(opts, 'skip') || flagged(opts, 'todo');
  const chain = R.stack.concat(n);
  if (kind === 'test') {
    R.rows.push({ id: chain.join(' > '), skipped });
    return Promise.resolve();
  }
  R.stack.push(n);
  try {
    // a skipped suite skips everything inside it
    const before = R.rows.length;
    if (typeof fn === 'function') fn({ name: n });
    if (skipped) for (let i = before; i < R.rows.length; i++) R.rows[i].skipped = true;
  } finally { R.stack.pop(); }
  return Promise.resolve();
}

function make(kind) {
  const f = (name, a, b) => record(kind, 'run', name, a, b);
  f.skip = (name, a, b) => record(kind, 'skip', name, a, b);
  f.todo = (name, a, b) => record(kind, 'todo', name, a, b);
  f.only = (name, a, b) => record(kind, 'run', name, a, b);
  return f;
}

export const test = make('test');
export const it = test;
export const describe = make('suite');
export const suite = describe;
export const before = noop;
export const after = noop;
export const beforeEach = noop;
export const afterEach = noop;
export const run = noop;
const deep = () => new Proxy(function () {}, { get: () => deep(), apply: () => undefined });
export const mock = deep();
for (const k of ['before', 'after', 'beforeEach', 'afterEach']) test[k] = noop;
Object.assign(test, { describe, suite, it: test, test, mock, run });
export default test;
