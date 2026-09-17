// Asserts on exactly what Gemini receives, without calling the API.
// Background: the 2026-09-15 prompt review found the write-section prompt
// requesting self-review scores that came back at a flat maximum on all 28
// recorded calls, a `words.md` section that was always empty, the author's
// voice described but never shown, and a synthesize rule that protected only
// citations containing a year (Hebrew citations carry none).

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, mkdir, utimes } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import * as path from 'node:path';
import { buildWriteSectionSystem, WriteSectionInput } from '../src/tools/write_section.js';
import { getBundle, clearBundleCache, parseExemplarsFile, type CalibrationBundle } from '../src/bundle.js';
import SYNTHESIZE_TEMPLATE from '../src/prompts/synthesize.md';
import EDIT_TEMPLATE from '../src/prompts/edit.md';

const BUNDLE: CalibrationBundle = {
  voice: 'VOICE-PROFILE-TEXT',
  fingerprint: '{"summary": "FINGERPRINT-TEXT"}',
  exemplars: ['EXEMPLAR-ONE (מקור, עמ\' 3). פסקה.', 'EXEMPLAR-TWO (שם, עמ\' 4). פסקה.'],
  exemplarSource: 'voice-exemplars.md',
  antiAi: 'ANTI-AI-LIST',
  positiveTerminology: 'TERMINOLOGY-LIST',
  targetLanguage: 'hebrew',
};

function input(): WriteSectionInput {
  return WriteSectionInput.parse({
    section_brief: {
      title: 'T',
      description: 'D',
      argument_role: 'critique',
      paragraph_count: 3,
      is_intro: false,
      is_conclusion: false,
      paragraph_word_ceiling: 180,
      thesis: 'THESIS-TEXT',
      claim: 'CLAIM-TEXT',
    },
    sources: [{ source_id: 's1', excerpt: 'SOURCE-EXCERPT' }],
    evidence_ownership: { p1: ['s1'] },
    banned_terms: [{ term: 'BANNED-WORD' }],
    target_language: 'Hebrew',
    citation_style: 'inline-parenthetical',
  });
}

describe('write-section system prompt', () => {
  const system = buildWriteSectionSystem(input(), BUNDLE);

  test('every placeholder is filled', () => {
    assert.equal(/\{\{\w+\}\}/.test(system), false, system.match(/\{\{\w+\}\}/g)?.join(', '));
  });

  test('shows the author\'s real prose as numbered examples', () => {
    assert.ok(system.includes('<voice_examples>'));
    assert.ok(system.includes('<example n="1">\nEXEMPLAR-ONE'));
    assert.ok(system.includes('<example n="2">\nEXEMPLAR-TWO'));
  });

  test('reference lists first, voice next, task data, instructions last', () => {
    const order = ['ANTI-AI-LIST', 'TERMINOLOGY-LIST', 'VOICE-PROFILE-TEXT', 'FINGERPRINT-TEXT', 'EXEMPLAR-ONE', '<section_plan>', 'SOURCE-EXCERPT', '<instructions>', '"paragraphs"'];
    const positions = order.map((marker) => system.indexOf(marker));
    positions.forEach((pos, i) => assert.ok(pos >= 0, order[i] + ' missing'));
    for (let i = 1; i < positions.length; i += 1) {
      assert.ok(positions[i - 1] < positions[i], order[i - 1] + ' should precede ' + order[i]);
    }
  });

  test('carries thesis, claim, banned terms, paragraph count and the ceiling as a maximum', () => {
    for (const marker of ['THESIS-TEXT', 'CLAIM-TEXT', 'BANNED-WORD', '3 paragraphs', '180 words per paragraph is a hard maximum']) {
      assert.ok(system.includes(marker), marker);
    }
  });

  test('asks for no self-review scores and has no linking-words section', () => {
    assert.equal(/self_review|self-review/i.test(system), false);
    assert.equal(system.includes('words.md'), false);
  });

  test('routes missing citation details to gaps, never into the prose', () => {
    assert.ok(system.includes('"gaps"'));
    assert.ok(system.includes('Never write a note about the missing detail inside the article text'));
  });

  test('Hebrew citation form is year-free', () => {
    assert.ok(system.includes("(מחבר, עמ' N)"));
  });
});

describe('synthesize and edit prompts', () => {
  test('synthesize protects year-less Hebrew parenthetical citations', () => {
    assert.ok(SYNTHESIZE_TEMPLATE.includes('with or without a year'));
    assert.ok(SYNTHESIZE_TEMPLATE.includes("(מחבר, עמ' 12)"));
    assert.equal(SYNTHESIZE_TEMPLATE.includes('that contains a year (citation)'), false);
  });

  test('synthesize and edit point at the voice examples', () => {
    assert.ok(SYNTHESIZE_TEMPLATE.includes('<voice_examples>'));
    assert.ok(EDIT_TEMPLATE.includes('<voice_examples>'));
  });
});

describe('calibration bundle', () => {
  test('parseExemplarsFile splits on --- and drops headings and comments', () => {
    const md = '# Voice exemplars\n<!-- generated -->\n\nFirst paragraph.\n\n---\nSecond paragraph.\n';
    assert.deepEqual(parseExemplarsFile(md), ['First paragraph.', 'Second paragraph.']);
  });

  test('falls back to fingerprint excerpts, then picks up a new exemplars file without a restart', async () => {
    const project = await mkdtemp(path.join(tmpdir(), 'aw-bundle-'));
    await mkdir(path.join(project, '.academic-helper'), { recursive: true });
    await writeFile(path.join(project, 'AUTHOR_VOICE.md'), '# Voice\nvoice text');
    await writeFile(
      path.join(project, '.academic-helper', 'profile.md'),
      '## Style Fingerprint\n\n```json\n{"dimensions": {"representative_excerpts": ["FP-SENTENCE."]}}\n```\n',
    );
    const prevProject = process.env.CLAUDE_PROJECT_DIR;
    const prevPlugin = process.env.CLAUDE_PLUGIN_ROOT;
    process.env.CLAUDE_PROJECT_DIR = project;
    process.env.CLAUDE_PLUGIN_ROOT = project; // no reference lists there; not under test
    try {
      clearBundleCache();
      const first = await getBundle('hebrew');
      assert.equal(first.exemplarSource, 'fingerprint');
      assert.deepEqual(first.exemplars, ['FP-SENTENCE.']);

      const exemplarsPath = path.join(project, '.academic-helper', 'voice-exemplars.md');
      await writeFile(exemplarsPath, 'REAL-PARAGRAPH.\n---\nSECOND-PARAGRAPH.\n');
      const later = new Date(Date.now() + 5000);
      await utimes(exemplarsPath, later, later);

      const second = await getBundle('hebrew');
      assert.equal(second.exemplarSource, 'voice-exemplars.md');
      assert.deepEqual(second.exemplars, ['REAL-PARAGRAPH.', 'SECOND-PARAGRAPH.']);
    } finally {
      process.env.CLAUDE_PROJECT_DIR = prevProject;
      process.env.CLAUDE_PLUGIN_ROOT = prevPlugin;
      clearBundleCache();
    }
  });
});
