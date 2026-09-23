import thresholds from '../../thresholds.json' with { type: 'json' };

export const stepIds = ['proofread.find','proofread.verify','proofread.memo','evidence.extract','write.draft','write.synthesize','voice.moves','revise.classify','ocr','edit'] as const;
export type StepId = typeof stepIds[number];
export type Route = { provider: 'gemini' | 'openrouter' | 'code'; model: string; maxOutputTokens: number; concurrency: number };
const modelTable = thresholds.models as Record<StepId, Route>;
export function routeFor(step: StepId): Route { const route = modelTable[step]; if (!route) throw new Error(`ERROR ${step}: no route configured`); return route; }
