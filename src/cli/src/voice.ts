import { appendFileSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join, resolve, basename } from 'node:path';
import { execFileSync } from 'node:child_process';
import { dataDir as configuredDataDir, projectDir } from './paths.ts';
import { allowedEnv } from './library/backends.ts';
import { callGemini } from './gemini.ts';
import { AwError, Budget } from './ledger.ts';
import thresholds from '../../thresholds.json' with { type: 'json' };

let dataOverride: string | undefined;
export function __setDataDir(path: string): void { dataOverride = resolve(path); }
function store(): string { return join(dataOverride ?? configuredDataDir(), 'voice'); }
type Exemplar = { id: string; source: string; text: string };
type Pair = { before: string; after: string; source?: string };
export function appendVoicePair(pair: Pair, dataRoot?: string): void {
  const dir = join(dataRoot ?? dataOverride ?? configuredDataDir(), 'voice');
  mkdirSync(dir, { recursive: true });
  appendFileSync(join(dir, 'pairs.jsonl'), `${JSON.stringify(pair)}\n`, 'utf8');
}
export function writeVoiceStyleWords(value: unknown, dataRoot?: string): void {
  const dir = join(dataRoot ?? dataOverride ?? configuredDataDir(), 'voice');
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'style-words.json'), JSON.stringify(value, null, 2), 'utf8');
}
function readJsonl<T>(path: string): T[] { if (!existsSync(path)) return []; return readFileSync(path, 'utf8').split(/\r?\n/).filter(Boolean).map(line => JSON.parse(line) as T); }
function sha(content: string): string { return createHash('sha256').update(content).digest('hex'); }
function refreshVersion(dir: string): string {
  const profilePath = join(dir, 'profile.json');
  const profile = JSON.parse(readFileSync(profilePath, 'utf8')) as Record<string, unknown>;
  const names = ['exemplars.jsonl', 'pairs.jsonl', 'style-words.json', 'rules.md'];
  const version = sha(names.map(name => existsSync(join(dir, name)) ? readFileSync(join(dir, name), 'utf8') : '').join('\n'));
  profile.voiceVersion = version;
  writeFileSync(profilePath, JSON.stringify(profile, null, 2));
  return version;
}
function paragraphs(text: string): string[] { return text.split(/\n\s*\n/).map(p => p.replace(/^#+\s*/, '').trim()).filter(Boolean); }
export async function voiceBundle(options: { n: number; pairs: number; runId: string }): Promise<{ exemplars: Exemplar[]; pairs: Pair[]; path: string }> {
  const dir = store();
  if (!existsSync(join(dir, 'profile.json'))) throw new AwError('ERROR', 'voice.bundle', 'exit 3 no voice store — run: aw voice pull (or /academic-writer:voice)');
  const all = readJsonl<Exemplar>(join(dir, 'exemplars.jsonl'));
  const chosen: Exemplar[] = [];
  const sources = new Set<string>();
  const perSource = thresholds.voice.bundle.maxPerSource;
  let seed = Number.parseInt(sha(options.runId).slice(0, 8), 16) || 1;
  while (all.length && chosen.length < options.n) {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    const index = seed % all.length;
    const item = all.splice(index, 1)[0];
    const sourceCount = chosen.filter(exemplar => exemplar.source === item?.source).length;
    if (!item || sources.has(item.source) && sourceCount >= perSource) continue;
    sources.add(item.source); chosen.push(item);
  }
  const pairs = readJsonl<Pair>(join(dir, 'pairs.jsonl')).slice(-options.pairs);
  const out = join(dir, `bundle-${sha(options.runId).slice(0, 12)}.json`);
  writeFileSync(out, JSON.stringify({ exemplars: chosen, pairs, rules: readFileSync(join(dir, 'rules.md'), 'utf8'), styleWords: JSON.parse(readFileSync(join(dir, 'style-words.json'), 'utf8')) }, null, 2));
  return { exemplars: chosen, pairs, path: out };
}
export function voiceMigrate(from: string): string {
  const dir = store(); mkdirSync(dir, { recursive: true });
  const source = resolve(from);
  // A first-time author has no legacy voice file; start an empty store they fill with exemplars.
  const authorPath = join(source, 'AUTHOR_VOICE.md');
  const author = existsSync(authorPath) ? readFileSync(authorPath, 'utf8') : '';
  const fingerprintPath = join(source, '.voice', 'fingerprint.md');
  const exemplarsPath = join(source, '.academic-helper', 'voice-exemplars.md');
  const fingerprint = existsSync(fingerprintPath) ? readFileSync(fingerprintPath, 'utf8') : '';
  const rawExemplars = existsSync(exemplarsPath) ? readFileSync(exemplarsPath, 'utf8') : '';
  const version = sha(author + fingerprint + rawExemplars);
  writeFileSync(join(dir, 'profile.json'), JSON.stringify({ schemaVersion: 1, voiceVersion: version, authorVoice: author, fingerprint }, null, 2));
  const rows = paragraphs(rawExemplars).filter(p => p !== '# Voice exemplars').map((text, index) => ({ id: `migrated-${index + 1}`, source: `migration-${index + 1}`, text }));
  writeFileSync(join(dir, 'exemplars.jsonl'), rows.map(r => JSON.stringify(r)).join('\n') + (rows.length ? '\n' : ''));
  for (const file of ['pairs.jsonl', 'CHANGELOG.jsonl']) if (!existsSync(join(dir, file))) writeFileSync(join(dir, file), '');
  if (!existsSync(join(dir, 'style-words.json'))) writeFileSync(join(dir, 'style-words.json'), JSON.stringify({ banned: [], capped: [], filler: [] }, null, 2));
  if (!existsSync(join(dir, 'rules.md'))) writeFileSync(join(dir, 'rules.md'), author.split('\n').slice(0, thresholds.voice.bundle.maxRuleLines).join('\n'));
  return dir;
}
export function voiceCandidates(corpus: string): Exemplar[] {
  const files = readdirSync(resolve(corpus), { withFileTypes: true }).filter(entry => entry.isFile() && entry.name.endsWith('.md'));
  return files.flatMap(file => paragraphs(readFileSync(join(resolve(corpus), file.name), 'utf8')).map((text, i) => ({ id: `${basename(file.name)}-${i + 1}`, source: file.name, text }))).filter(e => e.text.split(/\s+/).length >= thresholds.voice.exemplars.minWords);
}
export async function voiceMoves(runId: string): Promise<string> {
  const dir = store();
  const profile = readFileSync(join(dir, 'profile.json'), 'utf8');
  const exemplars = readJsonl<Exemplar>(join(dir, 'exemplars.jsonl'));
  const result = await callGemini({ step: 'voice.moves', system: `Describe concise reusable author writing moves. Return JSON with a rules string of no more than ${thresholds.voice.bundle.maxRuleLines} lines.`, parts: [profile, JSON.stringify(exemplars)], runId, budget: new Budget(runId, thresholds.budget.voiceMoves), responseSchema: { type: 'OBJECT', properties: { rules: { type: 'STRING' } }, required: ['rules'] } });
  const parsed = result.json as { rules?: unknown };
  if (typeof parsed.rules !== 'string') throw new AwError('ERROR', 'voice.moves', 'missing rules verdict');
  const rules = parsed.rules.split('\n').slice(0, thresholds.voice.bundle.maxRuleLines).join('\n');
  writeFileSync(join(dir, 'rules.md'), rules + '\n');
  refreshVersion(dir);
  return rules;
}
export function voiceSync(direction: 'push' | 'pull'): string {
  const dir = store(); mkdirSync(dir, { recursive: true });
  try {
    const profileText = readFileSync(join(projectDir(), '.academic-helper', 'profile.md'), 'utf8');
    const authorKey = /^author_key:\s*["']?([^\s"']+)/m.exec(profileText)?.[1];
    if (!authorKey) throw new AwError('ERROR', `voice.${direction}`, 'author_key missing from project profile');
    const title = `Voice Store — ${authorKey}`;
    const names = ['profile.json', 'exemplars.jsonl', 'pairs.jsonl', 'style-words.json', 'rules.md', 'CHANGELOG.jsonl'];
    const readStore = (): Record<string, string> => Object.fromEntries(names.map(name => [name, existsSync(join(dir, name)) ? readFileSync(join(dir, name), 'utf8') : '']));
    const writeStore = (files: Record<string, string>): void => { for (const name of names) writeFileSync(join(dir, name), files[name] ?? ''); };
    const local = readStore();
    const previousVersion = (local['profile.json'] ? JSON.parse(local['profile.json']) as { voiceVersion?: string } : {}).voiceVersion;
    const currentVersion = refreshVersion(dir);
    if (currentVersion !== previousVersion) writeFileSync(join(dir, 'CHANGELOG.jsonl'), `${local['CHANGELOG.jsonl'] ?? ''}${JSON.stringify({ voiceVersion: currentVersion, at: new Date().toISOString() })}\n`);
    local['profile.json'] = readFileSync(join(dir, 'profile.json'), 'utf8');
    local['CHANGELOG.jsonl'] = readFileSync(join(dir, 'CHANGELOG.jsonl'), 'utf8');
    const localProfile = local['profile.json'] ? JSON.parse(local['profile.json']) as { voiceVersion?: string } : {};
    const listingText = execFileSync('trove', ['items', 'list', '--json'], { encoding: 'utf8', env: allowedEnv(process.env, 'trove') });
    const listing = JSON.parse(listingText) as { items?: Array<{ id?: string; title?: string }> };
    const item = listing.items?.find(row => row.title === title && typeof row.id === 'string');
    if (direction === 'pull' && !item?.id) throw new AwError('ERROR', 'voice.pull', 'no Trove voice store found');
    let remote: Record<string, string> | undefined;
    if (item?.id) {
      const text = execFileSync('trove', ['items', 'get', item.id], { encoding: 'utf8', env: allowedEnv(process.env, 'trove') });
      remote = JSON.parse(text) as Record<string, string>;
    }
    if (direction === 'pull') {
      if (!remote) throw new AwError('ERROR', 'voice.pull', 'missing remote store');
      const remoteProfile = remote['profile.json'] ? JSON.parse(remote['profile.json']) as { voiceVersion?: string } : {};
      const merged = { ...remote };
      if (localProfile.voiceVersion && remoteProfile.voiceVersion && localProfile.voiceVersion > remoteProfile.voiceVersion) Object.assign(merged, local);
      const changelog = [...new Set([...(remote['CHANGELOG.jsonl'] ?? '').split('\n'), ...(local['CHANGELOG.jsonl'] ?? '').split('\n')].filter(Boolean))].join('\n');
      merged['CHANGELOG.jsonl'] = changelog ? `${changelog}\n` : '';
      writeStore(merged);
      return `voice pull: synchronized ${title}`;
    }
    const body = JSON.stringify(local, null, 2);
    const remoteProfile = remote?.['profile.json'] ? JSON.parse(remote['profile.json']) as { voiceVersion?: string } : {};
    if (localProfile.voiceVersion && remoteProfile.voiceVersion && remoteProfile.voiceVersion > localProfile.voiceVersion && remote) {
      local['CHANGELOG.jsonl'] = [...new Set([...(remote['CHANGELOG.jsonl'] ?? '').split('\n'), ...(local['CHANGELOG.jsonl'] ?? '').split('\n')].filter(Boolean))].join('\n') + '\n';
    }
    const file = join(dir, '.trove-voice.md');
    writeFileSync(file, body);
    if (item?.id) execFileSync('trove', ['items', 'put', item.id, '-f', file], { encoding: 'utf8', env: allowedEnv(process.env, 'trove') });
    else execFileSync('trove', ['items', 'import', file, '--title', title], { encoding: 'utf8', env: allowedEnv(process.env, 'trove') });
    return `voice push: synchronized ${title}`;
  } catch (error) {
    if (error instanceof AwError) throw error;
    throw new AwError('ERROR', `voice.${direction}`, error instanceof Error ? error.message : 'Trove sync failed');
  }
}
export function voiceProjectDir(): string { return projectDir(); }
