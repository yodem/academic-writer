#!/usr/bin/env node
import * as p from '@clack/prompts';
import { execSync } from 'child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';

function detect(cmd) {
  try { execSync(cmd, { stdio: 'pipe' }); return true; } catch { return false; }
}

async function main() {
  console.log('');
  p.intro('Academic Writer — Setup');

  // Check existing profile
  const profilePath = '.academic-writer/profile.json';
  let existingProfile = null;

  if (existsSync(profilePath)) {
    const action = await p.select({
      message: 'You already have a profile. What would you like to do?',
      options: [
        { value: 'update', label: 'Update it' },
        { value: 'fresh', label: 'Start fresh' },
      ],
    });
    if (p.isCancel(action)) { p.cancel('Setup cancelled.'); process.exit(0); }
    if (action === 'update') {
      existingProfile = JSON.parse(readFileSync(profilePath, 'utf-8'));
    }
  }

  // Step 1: Field of study
  const fieldOfStudy = await p.text({
    message: 'Step 1 of 4 — Field of Study\nWhat is your field of study and area of specialization?',
    placeholder: 'e.g. Early Modern Jewish Philosophy',
    defaultValue: existingProfile?.fieldOfStudy ?? '',
    validate: (v) => v.trim().length < 3 ? 'Please be more specific.' : undefined,
  });
  if (p.isCancel(fieldOfStudy)) { p.cancel('Setup cancelled.'); process.exit(0); }

  // Step 2: Language
  const langChoice = await p.select({
    message: 'Step 2 of 4 — Article Language\nWhat language will you write your articles in?',
    options: [
      { value: 'Hebrew', label: 'Hebrew' },
      { value: 'English', label: 'English' },
      { value: 'other', label: 'Other (specify)' },
    ],
    initialValue: existingProfile?.targetLanguage === 'Hebrew' || existingProfile?.targetLanguage === 'English'
      ? existingProfile.targetLanguage
      : 'Hebrew',
  });
  if (p.isCancel(langChoice)) { p.cancel('Setup cancelled.'); process.exit(0); }

  let targetLanguage = langChoice;
  if (langChoice === 'other') {
    const custom = await p.text({ message: 'Specify your language:' });
    if (p.isCancel(custom)) { p.cancel('Setup cancelled.'); process.exit(0); }
    targetLanguage = custom;
  }

  // Step 3: Citation style
  const citationStyle = await p.select({
    message: 'Step 3 of 4 — Citation Style\nWhich citation style do you use in your work?',
    options: [
      {
        value: 'inline-parenthetical',
        label: 'Inline Parenthetical',
        hint: '(Author, Title, Page) in running text — recommended for Hebrew',
      },
      {
        value: 'chicago',
        label: 'Chicago/Turabian',
        hint: 'footnotes — most common in English Humanities',
      },
      { value: 'mla', label: 'MLA' },
      { value: 'apa', label: 'APA' },
    ],
    initialValue: existingProfile?.citationStyle ?? 'inline-parenthetical',
  });
  if (p.isCancel(citationStyle)) { p.cancel('Setup cancelled.'); process.exit(0); }

  // Step 4: Tool detection
  const s = p.spinner();
  s.start('Detecting available tools...');

  const ckDetected = detect('command -v ck');
  const vectorlessDetected = existsSync('../Agentic-Search-Vectorless/src');
  const cognetivyDetected = detect('command -v cognetivy');

  s.stop('Tool detection complete.');

  const initialTools = [
    ...(ckDetected ? ['candlekeep'] : []),
    ...(vectorlessDetected ? ['agentic-search-vectorless'] : []),
    ...(cognetivyDetected ? ['cognetivy'] : []),
  ];

  const selectedTools = await p.multiselect({
    message: 'Step 4 of 4 — Data Services\nSelect which tools to enable:',
    options: [
      {
        value: 'candlekeep',
        label: 'Candlekeep',
        hint: ckDetected ? '✓ detected' : 'not found — install from github.com/romiluz13/candlekeep',
      },
      {
        value: 'agentic-search-vectorless',
        label: 'Agentic-Search-Vectorless',
        hint: vectorlessDetected ? '✓ detected at ../Agentic-Search-Vectorless/' : 'not found at ../Agentic-Search-Vectorless/',
      },
      {
        value: 'cognetivy',
        label: 'Cognetivy',
        hint: cognetivyDetected ? '✓ detected' : 'workflow audit trail',
      },
    ],
    initialValues: initialTools,
    required: false,
  });
  if (p.isCancel(selectedTools)) { p.cancel('Setup cancelled.'); process.exit(0); }

  // Create folders
  mkdirSync('past-articles', { recursive: true });
  mkdirSync('.academic-writer', { recursive: true });
  mkdirSync('.cognetivy/runs', { recursive: true });
  mkdirSync('.cognetivy/events', { recursive: true });

  // Build and save profile
  const now = new Date().toISOString();
  const isHebrew = targetLanguage === 'Hebrew';

  const profile = {
    fieldOfStudy: fieldOfStudy.trim(),
    targetLanguage,
    citationStyle,
    outputFormatPreferences: existingProfile?.outputFormatPreferences ?? {
      font: isHebrew ? 'David' : 'Times New Roman',
      bodySize: 11,
      titleSize: 16,
      headingSize: 13,
      lineSpacing: 1.5,
      marginInches: 1.0,
      alignment: 'justify',
      rtl: isHebrew,
    },
    styleFingerprint: existingProfile?.styleFingerprint ?? null,
    tools: {
      candlekeep: { enabled: selectedTools.includes('candlekeep') },
      'agentic-search-vectorless': {
        enabled: selectedTools.includes('agentic-search-vectorless'),
        path: '../Agentic-Search-Vectorless',
      },
      'mongodb-agent-skills': { enabled: false },
      cognetivy: { enabled: selectedTools.includes('cognetivy') },
    },
    sources: existingProfile?.sources ?? [],
    createdAt: existingProfile?.createdAt ?? now,
    updatedAt: now,
  };

  writeFileSync(profilePath, JSON.stringify(profile, null, 2));

  p.note(
    `Your folders are ready:\n` +
    `  past-articles/  ← drop 5–10 of your published papers here (PDF or DOCX)\n` +
    `  .academic-writer/profile.json  ← your profile (saved)`,
    'Folders created'
  );

  p.outro(
    'Setup complete! Now open Claude Code in this folder and run:\n' +
    '  /academic-writer-init\n' +
    'Claude will analyze your writing style from the papers in past-articles/.'
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
