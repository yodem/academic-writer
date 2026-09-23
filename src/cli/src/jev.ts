export type JevResult = { answer: string; confidence: number };
export type JevQuestion = { question: string; options: string[]; context: string };
type JevAnswer = { type?: string; noul?: number; choice?: string; score?: number; confidence?: number };
export async function askJev(input: JevQuestion): Promise<JevResult> {
  const key = (process.env.JEV_API_KEY ?? '').trim();
  if (!key) throw new Error('ERROR Jev: missing JEV_API_KEY');
  const thresholds = (await import('../../thresholds.json', { with: { type: 'json' } })).default as { jev: { model: string; yesProbability: number; scoreMaximum: number } };
  const response = await fetch('https://api.typesafe.ai/v1/systemone', {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    // Request shape matches the working jev-ask client: choice questions carry `instructions` and a
    // `criteria` map keyed by option (the API rejects `question`/`options`).
    body: JSON.stringify({ state: input.context, questions: { q: jevQuestion(input) }, model: thresholds.jev.model }),
  });
  if (!response.ok) throw new Error(`ERROR Jev: HTTP ${response.status}`);
  const payload = await response.json() as { answers?: { q?: JevAnswer } };
  const answer = payload.answers?.q;
  if (!answer) throw new Error('ERROR Jev: missing answer');
  const selected = typeof answer.choice === 'string' ? answer.choice : typeof answer.noul === 'number' ? (answer.noul >= thresholds.jev.yesProbability ? 'yes' : 'no') : undefined;
  const confidence = typeof answer.confidence === 'number' ? answer.confidence : typeof answer.noul === 'number' ? Math.max(answer.noul, 1 - answer.noul) : typeof answer.score === 'number' ? answer.score / thresholds.jev.scoreMaximum : undefined;
  if (selected === undefined) throw new Error('ERROR Jev: malformed answer');
  if (confidence === undefined || !Number.isFinite(confidence) || confidence < 0 || confidence > 1) throw new Error('ERROR Jev: missing or invalid confidence');
  return { answer: selected, confidence };
}

export function jevQuestion(input: JevQuestion): { type: 'choice'; instructions: string; criteria: Record<string, null> } {
  return { type: 'choice', instructions: input.question, criteria: Object.fromEntries(input.options.map((o) => [o, null])) };
}
