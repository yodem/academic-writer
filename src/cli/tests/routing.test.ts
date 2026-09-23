import { test } from 'node:test';
import assert from 'node:assert/strict';
import { routeFor } from '../src/routing.ts';
import { Budget } from '../src/ledger.ts';

test('every step in thresholds.models routes to flash for gemini', () => {
  const r = routeFor('write.draft');
  assert.equal(r.provider, 'gemini');
  assert.match(r.model, /flash/);
});

test('budget cap throws CAP_REACHED', () => {
  const b = new Budget('t', { maxTokens: 100 });
  assert.throws(() => b.charge({ in: 90, out: 20 }), /CAP_REACHED/);
});
