import type { HookInput, HookResult } from '../types.js';
import { loadProfile } from '../lib/profile.js';
import type { StyleFingerprint } from '../types.js';

export function loadFingerprint(input: HookInput): HookResult {
  const projectDir = input.project_dir ?? process.env['CLAUDE_PROJECT_DIR'] ?? '.';
  const profile = loadProfile(projectDir);

  if (!profile) {
    return { continue: true, suppressOutput: true };
  }

  const fp = profile.styleFingerprint;
  if (!fp) {
    return {
      continue: true,
      systemMessage:
        'Academic Writer: Profile exists but has no style fingerprint. Consider re-running /academic-writer-init.',
    };
  }

  const lines: string[] = [];
  lines.push('='.repeat(60));
  lines.push('ACADEMIC WRITER -- RESEARCHER PROFILE LOADED');
  lines.push('='.repeat(60));
  lines.push(`Field: ${profile.fieldOfStudy ?? 'Unknown'}`);
  lines.push(`Citation style: ${profile.citationStyle ?? 'Unknown'}`);
  lines.push('');

  if (fp.sentenceLevel && typeof fp.sentenceLevel === 'object') {
    formatExpandedFingerprint(fp, lines);
  } else {
    formatLegacyFingerprint(fp, lines);
  }

  lines.push('');
  lines.push('='.repeat(60));
  lines.push('This fingerprint is checked against every paragraph during writing.');
  lines.push('Update with /academic-writer-init (full) or edit .academic-helper/profile.md directly.');
  lines.push('='.repeat(60));

  return {
    continue: true,
    systemMessage: lines.join('\n'),
  };
}

function formatExpandedFingerprint(fp: StyleFingerprint, lines: string[]): void {
  const sl = fp.sentenceLevel;
  const vr = fp.vocabularyAndRegister;
  const ps = fp.paragraphStructure;
  const tv = fp.toneAndVoice;
  const tr = fp.transitions;
  const ci = fp.citations;
  const rp = fp.rhetoricalPatterns;

  lines.push('STYLE FINGERPRINT:');
  lines.push('-'.repeat(40));
  lines.push(`  Sentence length: ${sl?.averageLength ?? 'N/A'}`);
  lines.push(`  Structure variety: ${sl?.structureVariety ?? 'N/A'}`);
  lines.push(`  Passive voice: ${sl?.passiveVoice ?? 'N/A'}`);
  lines.push(`  Vocabulary: ${vr?.complexity ?? 'N/A'}`);
  lines.push(`  Register: ${vr?.registerLevel ?? 'N/A'}`);
  if (vr?.hebrewConventions) {
    lines.push(`  Hebrew conventions: ${vr.hebrewConventions}`);
  }
  lines.push(`  Paragraph pattern: ${ps?.pattern ?? 'N/A'}`);
  lines.push(`  Argument progression: ${ps?.argumentProgression ?? 'N/A'}`);
  lines.push(`  Tone: ${tv?.descriptors?.join(', ') ?? 'N/A'}`);
  lines.push(`  Author stance: ${tv?.authorStance ?? 'N/A'}`);
  lines.push(`  Citation density: ${ci?.density ?? 'N/A'} (~${ci?.footnotesPerParagraph ?? '?'}/paragraph)`);
  lines.push(`  Quote style: ${ci?.quoteLengthPreference ?? 'N/A'}`);
  if (rp?.common?.length) {
    lines.push(`  Rhetorical patterns: ${rp.common.join(', ')}`);
  }

  const pref = tr?.preferred;
  if (pref && Object.values(pref).some((v) => v?.length)) {
    lines.push('');
    lines.push('  Preferred transitions:');
    for (const [cat, phrases] of Object.entries(pref)) {
      if (phrases?.length) {
        lines.push(`    ${cat}: ${phrases.join(', ')}`);
      }
    }
  }

  const excerpts = fp.representativeExcerpts;
  if (excerpts?.length) {
    lines.push('');
    lines.push('  Representative excerpts (style targets):');
    for (let i = 0; i < Math.min(3, excerpts.length); i++) {
      const ex = excerpts[i];
      const display = ex.length > 150 ? ex.slice(0, 150) + '...' : ex;
      lines.push(`    ${i + 1}. "${display}"`);
    }
  }
}

function formatLegacyFingerprint(fp: StyleFingerprint, lines: string[]): void {
  lines.push('STYLE FINGERPRINT:');
  lines.push('-'.repeat(40));
  lines.push(`  Sentence length: ${fp.averageSentenceLength ?? 'N/A'} words`);
  lines.push(`  Vocabulary: ${fp.vocabularyComplexity ?? 'N/A'}`);
  lines.push(`  Passive voice: ${fp.passiveVoiceFrequency ?? 'N/A'}`);
  lines.push(`  Paragraph structure: ${fp.paragraphStructure_legacy ?? 'N/A'}`);
  lines.push(`  Citation density: ${fp.citationDensity ?? 'N/A'}`);
  if (fp.toneDescriptors?.length) {
    lines.push(`  Tone: ${fp.toneDescriptors.join(', ')}`);
  }
  if (fp.preferredTransitions?.length) {
    lines.push(`  Transitions: ${fp.preferredTransitions.slice(0, 8).join(', ')}`);
  }
  if (fp.sampleExcerpts?.length) {
    lines.push('');
    lines.push('  Representative excerpts:');
    for (let i = 0; i < Math.min(3, fp.sampleExcerpts.length); i++) {
      const ex = fp.sampleExcerpts[i];
      const display = ex.length > 150 ? ex.slice(0, 150) + '...' : ex;
      lines.push(`    ${i + 1}. "${display}"`);
    }
  }
}
