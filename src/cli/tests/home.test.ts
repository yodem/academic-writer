import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { homeDir, parseFrontmatter, parseSections, resolveProfile } from '../../hooks/src/lib/home.js';
import { loadProfile } from '../../hooks/src/lib/profile.js';

const FIXTURES = join(process.cwd(), '..', '..', 'tests', 'fixtures', 'profile');

function md(path: string, front: string, body = ''): void {
  mkdirSync(join(path, '..'), { recursive: true });
  writeFileSync(path, `---\n${front}\n---\n\n${body}`);
}

function tmp(): string {
  return mkdtempSync(join(tmpdir(), 'aw-home-'));
}

test('homeDir: ACADEMIC_HOME beats the pointer, no home gives null', () => {
  const data = tmp();
  writeFileSync(join(data, 'home.json'), JSON.stringify({ path: '/b' }));
  assert.equal(homeDir({ ACADEMIC_HOME: '/a', CLAUDE_PLUGIN_DATA: data }), '/a');
  assert.equal(homeDir({ CLAUDE_PLUGIN_DATA: data }), '/b');
  assert.equal(homeDir({}), null);
  assert.equal(homeDir({ CLAUDE_PLUGIN_DATA: tmp() }), null);
});

test('parsers match the shared fixture pair (same file the Python test reads)', () => {
  const text = readFileSync(join(FIXTURES, 'sample-profile.md'), 'utf-8');
  const expected = JSON.parse(readFileSync(join(FIXTURES, 'sample-profile.expected.json'), 'utf-8'));
  assert.deepEqual(parseFrontmatter(text), expected.frontmatter);
  assert.deepEqual(parseSections(text), expected.sections);
});

test('workspace overrides home; whole sections replace; home-only values survive', () => {
  const home = tmp();
  const ws = tmp();
  md(join(home, '.academic-helper', 'home.md'), 'name: X\ncitationStyle: chicago',
    '## Sources\n\n```json\n[{"id": "home"}]\n```\n\n## Tools\n\n```json\n{"a": 1}\n```\n');
  md(join(ws, '.academic-helper', 'profile.md'), 'citationStyle: apa',
    '## Sources\n\n```json\n[{"id": "ws"}]\n```\n');
  const r = resolveProfile(ws, { ACADEMIC_HOME: home });
  assert.equal(r.values['citationStyle'], 'apa');
  assert.equal(r.values['name'], 'X');
  assert.deepEqual(r.sections['sources'], [{ id: 'ws' }]);
  assert.deepEqual(r.sections['tools'], { a: 1 });
  assert.equal(r.home, home);
  assert.equal(r.homeMissing, false);
});

test('a dangling pointer sets homeMissing and keeps the workspace values', () => {
  const ws = tmp();
  md(join(ws, '.academic-helper', 'profile.md'), 'citationStyle: apa');
  const r = resolveProfile(ws, { ACADEMIC_HOME: join(tmp(), 'gone') });
  assert.equal(r.homeMissing, true);
  assert.equal(r.values['citationStyle'], 'apa');
});

test('loadProfile: null without a workspace profile, merged with home otherwise', () => {
  const home = tmp();
  const ws = tmp();
  const prev = process.env['ACADEMIC_HOME'];
  process.env['ACADEMIC_HOME'] = home;
  try {
    assert.equal(loadProfile(ws), null);
    md(join(home, '.academic-helper', 'home.md'), 'name: X\nfieldOfStudy: Philosophy\ncitationStyle: chicago');
    md(join(ws, '.academic-helper', 'profile.md'), 'citationStyle: apa\nworkspace: course\ncourse: cohen',
      '## Sources\n\n```json\n[{"id": "ws"}]\n```\n');
    const p = loadProfile(ws);
    assert.ok(p);
    assert.equal(p.citationStyle, 'apa');
    assert.equal(p.fieldOfStudy, 'Philosophy');
    assert.equal(p.name, 'X');
    assert.equal(p.workspace, 'course');
    assert.deepEqual(p.sources, [{ id: 'ws' }]);
    assert.equal(p.homeMissing, undefined);
  } finally {
    if (prev === undefined) delete process.env['ACADEMIC_HOME']; else process.env['ACADEMIC_HOME'] = prev;
  }
});

test('loadProfile reports the missing home path', () => {
  const ws = tmp();
  const gone = join(tmp(), 'gone');
  md(join(ws, '.academic-helper', 'profile.md'), 'citationStyle: apa');
  const prev = process.env['ACADEMIC_HOME'];
  process.env['ACADEMIC_HOME'] = gone;
  try {
    assert.equal(loadProfile(ws)?.homeMissing, gone);
  } finally {
    if (prev === undefined) delete process.env['ACADEMIC_HOME']; else process.env['ACADEMIC_HOME'] = prev;
  }
});

test('homeDir expands a leading ~ in ACADEMIC_HOME and in the pointer path', () => {
  const data = tmp();
  writeFileSync(join(data, 'home.json'), JSON.stringify({ path: '~/Academic' }));
  assert.equal(homeDir({ ACADEMIC_HOME: '~/Docs/A', HOME: '/h' }), join('/h', 'Docs/A'));
  assert.equal(homeDir({ ACADEMIC_HOME: '~', HOME: '/h' }), '/h');
  assert.equal(homeDir({ CLAUDE_PLUGIN_DATA: data, HOME: '/h' }), join('/h', 'Academic'));
  // only a leading ~ (alone or before a slash) is expanded
  assert.equal(homeDir({ ACADEMIC_HOME: '/x/~/y', HOME: '/h' }), '/x/~/y');
  assert.equal(homeDir({ ACADEMIC_HOME: '~other/y', HOME: '/h' }), '~other/y');
});

test('resolveProfile reads home.md through a ~ ACADEMIC_HOME', () => {
  const fakeHome = tmp();
  md(join(fakeHome, 'Academic', '.academic-helper', 'home.md'), 'name: Tilde');
  const r = resolveProfile(tmp(), { ACADEMIC_HOME: '~/Academic', HOME: fakeHome });
  assert.equal(r.values['name'], 'Tilde');
  assert.equal(r.homeMissing, false);
});
