import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { resolveVenueProfile } from '../src/proofread.js';

function layout(): { project: string; root: string } {
  const base = mkdtempSync(join(tmpdir(), 'aw-venue-'));
  const project = join(base, 'project'); const root = join(base, 'plugin');
  mkdirSync(join(project, '.academic-helper', 'venues'), { recursive: true });
  mkdirSync(join(root, 'venues'), { recursive: true });
  return { project, root };
}

test('the project venue profile wins over the bundled one with the same slug', () => {
  const { project, root } = layout();
  writeFileSync(join(project, '.academic-helper', 'venues', 'demo.md'), 'project copy');
  writeFileSync(join(root, 'venues', 'demo.md'), 'bundled copy');
  assert.equal(resolveVenueProfile('demo', project, root), 'project copy');
});

test('the bundled venue profile is used when the project has none, even with no project folder', () => {
  const { project, root } = layout();
  writeFileSync(join(root, 'venues', 'demo.md'), 'bundled copy');
  assert.equal(resolveVenueProfile('demo', project, root), 'bundled copy');
  assert.equal(resolveVenueProfile('demo', '', root), 'bundled copy');
});

test('no profile anywhere, no slug, or an empty plugin root gives an empty string', () => {
  const { project, root } = layout();
  assert.equal(resolveVenueProfile('missing', project, root), '');
  assert.equal(resolveVenueProfile(undefined, project, root), '');
  writeFileSync(join(root, 'venues', 'demo.md'), 'bundled copy');
  assert.equal(resolveVenueProfile('demo', project, ''), '');
});

test('a slug that would leave the venues folders resolves to nothing', () => {
  const { project, root } = layout();
  writeFileSync(join(root, 'secret.md'), 'outside');
  assert.equal(resolveVenueProfile('../secret', project, root), '');
  assert.equal(resolveVenueProfile('..', project, root), '');
  assert.equal(resolveVenueProfile('a/b', project, root), '');
});
