type SefariaText = { title: string; author: string; text: string };

function flattenText(value: unknown): string[] {
  return Array.isArray(value) ? value.flatMap(flattenText) : typeof value === 'string' ? [value] : [];
}

function stripHtml(value: string): string {
  return value.replace(/<[^>]*>/gu, '').trim();
}

function textFrom(value: unknown): string {
  return flattenText(value).map(stripHtml).filter(Boolean).join('\n');
}

function objectRecord(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null ? value as Record<string, unknown> : undefined;
}

function selectHebrewVersion(record: Record<string, unknown>): Record<string, unknown> | undefined {
  const versions = record.versions;
  if (!Array.isArray(versions)) return undefined;
  return versions.map(objectRecord).find((version) => version?.language === 'he');
}

export function parseSefariaResponse(payload: unknown, reference: string): SefariaText {
  const record = objectRecord(payload);
  if (!record) throw new Error('ERROR sefaria.fetch: invalid response');

  const version = selectHebrewVersion(record);
  const v3Text = version ? textFrom(version.text) : '';
  const legacyText = textFrom(record.he);
  const text = v3Text || legacyText;
  if (!text) throw new Error('ERROR sefaria.fetch: missing Hebrew text');

  const title = typeof record.ref === 'string' ? record.ref : reference;
  const author = version && typeof version.versionTitle === 'string' ? version.versionTitle : '';
  return { title, author, text };
}

export async function fetchSefaria(reference: string): Promise<SefariaText> {
  const response = await fetch(`https://www.sefaria.org/api/v3/texts/${encodeURIComponent(reference)}`);
  if (!response.ok) throw new Error(`ERROR sefaria.fetch: HTTP ${response.status}`);
  const payload: unknown = await response.json();
  return parseSefariaResponse(payload, reference);
}
