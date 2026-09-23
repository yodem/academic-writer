import { callGemini } from './gemini.ts';
import { callPi, piModelFor, piReady, type PiResult } from './pi.ts';
import type { StepId } from './routing.ts';
import { appendLedger } from './ledger.ts';
export { __setPiRunner, __setPiReady } from './pi.ts';
import thresholds from '../../thresholds.json' with { type: 'json' };

export type JudgeRequest = { step: StepId; prompt: string; schema: object; runId: string; finderProvider: 'gemini' | 'pi' };
export type JudgeResult = { json: unknown; sameFamily: boolean };
function matchesSchema(value: unknown, schema: object): boolean {
  const rule = schema as { type?: string; required?: string[]; properties?: Record<string, object>; enum?: unknown[] };
  if (rule.enum && !rule.enum.some((entry) => JSON.stringify(entry) === JSON.stringify(value))) return false;
  if (rule.type === 'object') {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
    const record = value as Record<string, unknown>;
    if (rule.required?.some((key) => !(key in record))) return false;
    return Object.entries(rule.properties ?? {}).every(([key, child]) => !(key in record) || matchesSchema(record[key], child));
  }
  if (rule.type === 'array') return Array.isArray(value);
  if (rule.type === 'string') return typeof value === 'string';
  if (rule.type === 'number' || rule.type === 'integer') return typeof value === 'number';
  if (rule.type === 'boolean') return typeof value === 'boolean';
  return true;
}
export async function judge(req: JudgeRequest): Promise<JudgeResult> {
  if (await piReady()) {
    const basePrompt = `${req.prompt}\nJSON schema:\n${JSON.stringify(req.schema)}`;
    let prompt = basePrompt;
    let lastError = 'invalid JSON';
    const judgeConfig = thresholds.judge as { validationAttempts: number };
    for (let attempt = 0; attempt < judgeConfig.validationAttempts; attempt++) {
      const started = Date.now();
      let usage = { in: 0, out: 0 };
      let exit: 'OK' | 'ERROR' = 'ERROR';
      try {
        let result: PiResult;
        try {
          result = await callPi(req.step, prompt, 'You are a constrained academic writing judge. Answer ONLY with one JSON object matching the schema in the prompt. Do not use tools. Preserve Hebrew quotations exactly; geresh and gershayim are abbreviation marks and must not be corrected.');
        } catch (error) {
          throw new Error(`ERROR ${req.step}: Pi model failure: ${error instanceof Error ? error.message : 'unknown error'}`);
        }
        usage = result.usage;
        const json: unknown = JSON.parse(result.finalText);
        if (!matchesSchema(json, req.schema)) throw new Error('JSON does not match schema');
        exit = 'OK';
        return { json, sameFamily: false };
      } catch (error) {
        lastError = error instanceof Error ? error.message : 'invalid JSON';
        if (lastError.startsWith(`ERROR ${req.step}:`)) throw error;
        prompt = `${basePrompt}\nValidation error: ${lastError}. Return one corrected JSON object.`;
      } finally {
        appendLedger({ run_id: req.runId, step: req.step, provider: 'pi', model: piModelFor(req.step), input_tokens: usage.in, output_tokens: usage.out, cost_usd: null, latency_ms: Date.now() - started, exit, same_family: false });
      }
    }
    throw new Error(`ERROR ${req.step}: ${lastError}`);
  }
  const result = await callGemini({ step: req.step, system: 'Return JSON matching the supplied schema.', parts: [req.prompt], responseSchema: req.schema, runId: req.runId });
  return { json: result.json, sameFamily: req.finderProvider === 'gemini' };
}
