import { GoogleGenAI } from '@google/genai';
import { routeFor, type StepId } from './routing.ts';
import { appendLedger, AwError, type Budget, type Usage } from './ledger.ts';

type Response = { text: string; finishReason: string; usage: Usage };
type Request = { step: StepId; system: string; parts: string[]; responseSchema?: object; runId: string; budget?: Budget };
type Transport = (request: Request & { model: string; key: string }) => Promise<Response>;
let transport: Transport = async (request) => {
  const ai = new GoogleGenAI({ apiKey: request.key });
  const result = await ai.models.generateContent({ model: request.model, contents: request.parts, config: { systemInstruction: request.system, responseMimeType: request.responseSchema ? 'application/json' : undefined, responseSchema: request.responseSchema } });
  return { text: result.text ?? '', finishReason: String(result.candidates?.[0]?.finishReason ?? ''), usage: { in: result.usageMetadata?.promptTokenCount ?? 0, out: result.usageMetadata?.candidatesTokenCount ?? 0 } };
};
export function __setTransport(value: Transport): void { transport = value; }
export { AwError };
export async function callGemini(req: Request): Promise<{ json: unknown; text: string; usage: Usage }> {
  const start = Date.now();
  const route = routeFor(req.step);
  let usage: Usage = { in: 0, out: 0 };
  let exit: 'OK' | 'ERROR' | 'CAP_REACHED' = 'ERROR';
  try {
    const key = (process.env.GOOGLE_API_KEY ?? '').trim();
    if (!key) throw new AwError('ERROR', req.step, 'missing Google API key');
    const response = await transport({ ...req, model: route.model, key });
    usage = response.usage;
    if (response.finishReason !== 'STOP') throw new AwError('ERROR', req.step, response.finishReason || 'missing finish reason');
    let json: unknown = null;
    if (req.responseSchema) { try { json = JSON.parse(response.text) as unknown; } catch { throw new AwError('ERROR', req.step, 'invalid JSON'); } }
    try { req.budget?.charge(response.usage, 0, req.step); } catch (error) { if (error instanceof AwError) exit = 'CAP_REACHED'; throw error; }
    exit = 'OK';
    return { json, text: response.text, usage: response.usage };
  } catch (error) {
    if (error instanceof AwError) throw error;
    throw new AwError('ERROR', req.step, error instanceof Error ? error.message : 'unknown model error');
  } finally {
    appendLedger({ run_id: req.runId, step: req.step, provider: 'gemini', model: route.model, input_tokens: usage.in, output_tokens: usage.out, cost_usd: null, latency_ms: Date.now() - start, exit, same_family: false });
  }
}
