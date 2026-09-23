import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { buildEvidence, __stubs } from '../src/evidence.ts';
import { setPathArguments } from '../src/paths.ts';

test('non-verbatim quotes are dropped; cache hit skips refetch', async () => {
  const root = mkdtempSync(join(tmpdir(), 'aw-evidence-'));
  setPathArguments(['--data-dir', root, '--project-dir', root]);
  let fetches = 0;
  __stubs({
    fetchCk: async () => { fetches += 1; return 'הרמב״ם כתב כי הנבואה היא שפע מאת האל.'; },
    extract: async () => ({ passages: [
      { id: 'p1', sourceId: 's1', locator: '1', quote: 'הנבואה היא שפע', gloss: '', relevance: 3 },
      { id: 'p2', sourceId: 's1', locator: '1', quote: 'הנבואה היא אור', gloss: '', relevance: 2 },
    ] }),
  });
  try {
    const first = await buildEvidence({ sources: ['s1'], runId: 't' });
    assert.deepEqual(first.passages.map((passage) => passage.id), ['p1']);
    await buildEvidence({ sources: ['s1'], runId: 't2' });
    assert.equal(fetches, 1);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
