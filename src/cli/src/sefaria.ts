export async function fetchSefaria(reference: string): Promise<{ title: string; author: string; text: string }> {
  const response = await fetch(`https://www.sefaria.org/api/v3/texts/${encodeURIComponent(reference)}`);
  if (!response.ok) throw new Error(`ERROR sefaria.fetch: HTTP ${response.status}`);
  const payload: unknown = await response.json();
  if (typeof payload !== 'object' || payload === null) throw new Error('ERROR sefaria.fetch: invalid response');
  const record = payload as Record<string, unknown>;
  const flatten = (value: unknown): string[] => Array.isArray(value) ? value.flatMap(flatten) : typeof value === 'string' ? [value] : [];
  const text = flatten(record.he).join('\n');
  if (!text) throw new Error('ERROR sefaria.fetch: missing Hebrew text');
  return { title: typeof record.ref === 'string' ? record.ref : reference, author: '', text };
}
