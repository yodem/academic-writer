import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseSefariaResponse } from '../src/sefaria.ts';

test('parseSefariaResponse reads Hebrew text from v3 versions array', () => {
  const fixture = JSON.parse(readFileSync(new URL('../../../tests/fixtures/sefaria-v3-pirkei-avot-1-6.json', import.meta.url), 'utf8')) as unknown;
  const result = parseSefariaResponse(fixture, 'Pirkei Avot 1:6');
  assert.equal(result.title, 'Pirkei Avot 1:6');
  assert.equal(result.author, 'Mishnah, Hebrew Test Version');
  assert.match(result.text, /עֲשֵׂה לְךָ רַב/u);
  assert.doesNotMatch(result.text, /<b>/u);
});

test('parseSefariaResponse falls back to legacy he field', () => {
  const result = parseSefariaResponse({ ref: 'Legacy 1:1', he: ['<i>שלום</i>', ['עולם']] }, 'Legacy 1:1');
  assert.equal(result.text, 'שלום\nעולם');
});
