/**
 * Thin wrapper around @google/genai that:
 *   - resolves API key from env or `.academic-helper/secrets.json`
 *   - resolves per-tool model defaults from `.academic-helper/profile.md > gemini.models`
 *   - splits unified `thinking_budget` into 2.5's `thinkingBudget` integer vs
 *     3.x's `thinkingLevel` categorical value
 *   - retries with exponential backoff on 5xx / 429 / network errors
 */
import { GoogleGenAI } from '@google/genai';
import { readFile } from 'node:fs/promises';
import * as path from 'node:path';
import {
  apiError,
  isRetryable,
  noCredentials,
  transient,
  type StructuredError,
} from './errors.js';

export type ToolName =
  | 'write_section'
  | 'synthesize'
  | 'edit'
  | 'calibrate_sample'
  | 'raw';

export interface ModelDefaults {
  model: string;
  thinking_budget: number;
}

/**
 * The model every tool uses unless something overrides it.
 *
 * Verified against the live ListModels API on 2026-09-04: `gemini-3.8-flash`
 * is the newest stable text model, and it is the ONLY 3.8 build published —
 * there is no `gemini-3.8-pro`. The newest pro-tier model of any generation is
 * `gemini-3.1-pro-preview`, which is a preview; a stable flash three
 * generations newer beats a preview pro for a pipeline that runs unattended.
 *
 * `thinking_budget` stays meaningful across the change: buildThinkingConfig()
 * maps a budget onto gemini-3's `thinkingLevel` rather than passing it
 * through, so the per-tool effort ordering below is preserved.
 *
 * NOT used by gemini_ocr, which is hard-pinned to gemini-2.5-flash for a
 * documented reason (see OCR_MODEL in gemini-client-ocr-helpers.ts) and must
 * not follow this default.
 */
export const DEFAULT_MODEL = 'gemini-3.8-flash';

const SPEC_DEFAULTS: Record<ToolName, ModelDefaults> = {
  write_section: { model: DEFAULT_MODEL, thinking_budget: 8192 },
  synthesize: { model: DEFAULT_MODEL, thinking_budget: 2048 },
  edit: { model: DEFAULT_MODEL, thinking_budget: 2048 },
  calibrate_sample: { model: DEFAULT_MODEL, thinking_budget: 1024 },
  raw: { model: DEFAULT_MODEL, thinking_budget: -1 },
};

/**
 * Resolution order for a tool's model, most specific first:
 *
 *   1. profile.md  gemini.models.<tool>.model   — per-tool, unchanged
 *   2. profile.md  gemini.defaultModel          — every tool at once
 *   3. env         GEMINI_DEFAULT_MODEL         — machine-level default
 *   4. DEFAULT_MODEL above
 *
 * The profile outranks the environment because it is the user's durable,
 * reviewed configuration; the env var exists so a machine (or a test) can set
 * a default without editing a profile that may not exist yet.
 */
function envDefaultModel(): string | undefined {
  const v = process.env['GEMINI_DEFAULT_MODEL'];
  return typeof v === 'string' && v.trim() ? v.trim() : undefined;
}

const RETRY_MAX_ATTEMPTS = 3;
const RETRY_BASE_MS = 1000;
const RETRY_FACTOR = 2;

let cachedKey: string | undefined = undefined; // undefined = uncached (or last resolution found nothing — never trusted as permanent)
let cachedDefaults: Partial<Record<ToolName, ModelDefaults>> | null = null;
let cachedClient: GoogleGenAI | null = null;

function projectDir(): string {
  return process.env.CLAUDE_PROJECT_DIR ?? process.cwd();
}

async function readSecretsKey(): Promise<string | undefined> {
  const secretsPath = path.join(projectDir(), '.academic-helper', 'secrets.json');
  try {
    const raw = await readFile(secretsPath, 'utf8');
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed === 'object' && parsed !== null) {
      const obj = parsed as Record<string, unknown>;
      // Canonical casing is GOOGLE_API_KEY (matches every write-path/setup doc);
      // accept lowercase google_api_key as a fallback for robustness.
      const raw =
        typeof obj['GOOGLE_API_KEY'] === 'string'
          ? (obj['GOOGLE_API_KEY'] as string)
          : typeof obj['google_api_key'] === 'string'
            ? (obj['google_api_key'] as string)
            : undefined;
      if (raw) {
        const v = raw.trim();
        return v.length > 0 ? v : undefined;
      }
    }
  } catch {
    // missing/unreadable/invalid JSON — treat as no key
  }
  return undefined;
}

export async function resolveApiKey(): Promise<string | undefined> {
  if (typeof cachedKey === 'string') return cachedKey;
  // No positive cache hit — always re-resolve rather than trusting a stale
  // "missing" result. This lets a key written mid-session (or a server
  // started before the key file existed) be picked up without a restart.
  // Only successful resolutions are cached.
  //
  // Precedence (highest first):
  //   1. USER_CONFIG_GOOGLE_API_KEY — the plugin's `userConfig.google_api_key`
  //      (manifests/academic-writer.json), substituted into this process's env
  //      as `${user_config.google_api_key}` by Claude Code. This is the
  //      PREFERRED path: Claude Code stores `sensitive: true` userConfig
  //      values in the OS keychain (or a protected credentials file), never
  //      plaintext in settings.json. An unconfigured optional userConfig
  //      field substitutes to an empty string, so this check falls through
  //      cleanly — it never throws or blocks the paths below.
  //   2. GOOGLE_API_KEY — plain shell/environment variable (pre-existing
  //      path; forwarded verbatim through the plugin manifest's `env` block
  //      too, so a shell export keeps working exactly as before).
  //   3. .academic-helper/secrets.json — project-local file written by
  //      /academic-writer:setup or /academic-writer:init (accepts both
  //      `GOOGLE_API_KEY` and lowercase `google_api_key` — see
  //      readSecretsKey() below; this is the casing-mismatch fix from a
  //      prior bug and must not regress).
  // All three paths are fully supported — userConfig is an ADDITIONAL,
  // preferred source, not a replacement. A researcher with a working
  // env-var or secrets.json setup today keeps working unchanged.
  const fromUserConfig = (process.env.USER_CONFIG_GOOGLE_API_KEY ?? '').trim();
  if (fromUserConfig) {
    cachedKey = fromUserConfig;
    return fromUserConfig;
  }
  const env = (process.env.GOOGLE_API_KEY ?? '').trim();
  if (env) {
    cachedKey = env;
    return env;
  }
  const fromSecrets = await readSecretsKey();
  if (fromSecrets) {
    cachedKey = fromSecrets;
    return fromSecrets;
  }
  return undefined;
}

/**
 * Test-only: clears the module-level key cache so resolveApiKey() re-checks
 * env/userConfig/secrets.json on the next call instead of returning a cached
 * value from a previous test. Never called from production code paths.
 */
export function __resetApiKeyCacheForTests(): void {
  cachedKey = undefined;
}

/**
 * Test-only companion to the above for the model-defaults cache, so a test can
 * point CLAUDE_PROJECT_DIR at a fresh fixture profile and have it re-read.
 */
export function __resetModelDefaultsCacheForTests(): void {
  cachedDefaults = null;
}

async function loadProfileModelDefaults(): Promise<Partial<Record<ToolName, ModelDefaults>>> {
  if (cachedDefaults) return cachedDefaults;
  const profilePath = path.join(projectDir(), '.academic-helper', 'profile.md');
  try {
    const raw = await readFile(profilePath, 'utf8');
    // Search for a fenced block under `## Gemini Models` OR a `gemini.models` JSON object.
    // We accept either ```json or ```yaml. We try JSON first; fall back to a tolerant key parse.
    const fenceMatch = /```(?:json|yaml|yml)\s*\n([\s\S]*?)\n```/gi;
    let m: RegExpExecArray | null;
    while ((m = fenceMatch.exec(raw)) !== null) {
      const body = m[1];
      try {
        const parsed: unknown = JSON.parse(body);
        const extracted = extractGeminiModels(parsed);
        if (extracted) {
          cachedDefaults = extracted;
          return extracted;
        }
      } catch {
        // not JSON; ignore in this minimal parser
      }
    }
  } catch {
    // no profile.md — fall through to spec defaults
  }
  cachedDefaults = {};
  return cachedDefaults;
}

function extractGeminiModels(parsed: unknown): Partial<Record<ToolName, ModelDefaults>> | null {
  if (typeof parsed !== 'object' || parsed === null) return null;
  const root = parsed as Record<string, unknown>;
  const gemini = root['gemini'];
  const geminiObj =
    gemini && typeof gemini === 'object' ? (gemini as Record<string, unknown>) : undefined;

  // `gemini.defaultModel` (or `gemini.model`) retargets every tool at once, so
  // a user changing model generation edits one line instead of five.
  const rawDefault = geminiObj?.['defaultModel'] ?? geminiObj?.['model'] ?? root['gemini.defaultModel'];
  const profileDefault =
    typeof rawDefault === 'string' && rawDefault.trim() ? rawDefault.trim() : undefined;

  const models =
    geminiObj && 'models' in geminiObj ? geminiObj['models'] : root['gemini.models'];

  if (typeof models !== 'object' || models === null) {
    if (!profileDefault) return null;
    // A profile that sets only a global default still overrides every tool.
    const only: Partial<Record<ToolName, ModelDefaults>> = {};
    for (const tool of Object.keys(SPEC_DEFAULTS) as ToolName[]) {
      only[tool] = { model: profileDefault, thinking_budget: SPEC_DEFAULTS[tool].thinking_budget };
    }
    return only;
  }
  const out: Partial<Record<ToolName, ModelDefaults>> = {};
  for (const tool of Object.keys(SPEC_DEFAULTS) as ToolName[]) {
    const entry = (models as Record<string, unknown>)[tool];
    if (typeof entry === 'object' && entry !== null) {
      const e = entry as Record<string, unknown>;
      const model = typeof e['model'] === 'string' ? (e['model'] as string) : undefined;
      const tb =
        typeof e['thinking_budget'] === 'number'
          ? (e['thinking_budget'] as number)
          : typeof e['thinkingBudget'] === 'number'
            ? (e['thinkingBudget'] as number)
            : undefined;
      if (model || tb !== undefined) {
        out[tool] = {
          model: model ?? profileDefault ?? SPEC_DEFAULTS[tool].model,
          thinking_budget: tb ?? SPEC_DEFAULTS[tool].thinking_budget,
        };
      }
    } else if (profileDefault) {
      // No per-tool entry, but a global default was declared.
      out[tool] = {
        model: profileDefault,
        thinking_budget: SPEC_DEFAULTS[tool].thinking_budget,
      };
    }
  }
  return Object.keys(out).length > 0 ? out : null;
}

export async function getDefaults(tool: ToolName): Promise<ModelDefaults> {
  const overrides = await loadProfileModelDefaults();
  const override = overrides[tool];
  if (override) return override;
  const envModel = envDefaultModel();
  return envModel
    ? { model: envModel, thinking_budget: SPEC_DEFAULTS[tool].thinking_budget }
    : SPEC_DEFAULTS[tool];
}

function thinkingLevelFromBudget(budget: number): 'low' | 'medium' | 'high' {
  if (budget < 0) return 'high';
  if (budget < 512) return 'low';
  if (budget < 4096) return 'medium';
  return 'high';
}

function isGemini3(model: string): boolean {
  return /^gemini-3(\.|-)/i.test(model);
}

interface ThinkingConfig {
  thinkingBudget?: number;
  thinkingLevel?: 'minimal' | 'low' | 'medium' | 'high';
}

export function buildThinkingConfig(model: string, budget: number): ThinkingConfig {
  if (isGemini3(model)) {
    if (budget < 0) return { thinkingLevel: 'high' };
    return { thinkingLevel: thinkingLevelFromBudget(budget) };
  }
  // 2.5 family — pass thinkingBudget as integer (-1 = dynamic)
  return { thinkingBudget: budget };
}

async function getClient(): Promise<GoogleGenAI> {
  if (cachedClient) return cachedClient;
  const key = await resolveApiKey();
  if (!key) throw noCredentials() as unknown as Error;
  cachedClient = new GoogleGenAI({ apiKey: key });
  return cachedClient;
}

/** A single part of a multimodal `contents` array — image (inline or
 * Files-API-referenced) or text. Vision callers (gemini_ocr) must order
 * image parts before the text part; see gemini-client-ocr-helpers.ts's
 * buildOcrParts(). */
export interface InlineImageContentPart {
  inlineData: { mimeType: string; data: string };
}
/** Files-API-referenced image, used once a page's image has been uploaded
 * via uploadFileToFilesApi()/uploadViaFilesApi() instead of inlined. */
export interface FileDataContentPart {
  fileData: { mimeType: string; fileUri: string };
}
export interface TextContentPart {
  text: string;
}
export type GenerateContentPart = InlineImageContentPart | FileDataContentPart | TextContentPart;

export interface GenerateArgs {
  system: string;
  /** Plain-text prompt. Mutually usable alongside/instead of `parts` — when
   * `parts` is provided it is sent as `contents` verbatim (already ordered
   * image-before-text by the caller) and `user` is ignored. */
  user: string;
  /** Optional multimodal `contents` array (image parts + a trailing text
   * part) for vision calls. Additive: existing text-only callers
   * (write_section, synthesize, edit, calibrate_sample, raw) never set this
   * and keep using `user`. */
  parts?: GenerateContentPart[];
  model: string;
  thinking_budget: number;
  temperature?: number;
  max_output_tokens?: number;
  response_mime_type?: string;
  /** Vision-call tuning (gemini_ocr only) — additive, all optional. */
  topK?: number;
  thinkingConfig?: { thinkingBudget?: number };
  generationConfig?: { mediaResolution?: string };
  responseSchema?: unknown;
}

export interface GenerateResult {
  text: string;
  finishReason: string;
  usage: {
    input_tokens: number;
    output_tokens: number;
    cached_tokens?: number;
  };
}

interface MaybeHttpError {
  status?: number;
  statusCode?: number;
  code?: string;
  message?: string;
}

function readHttpStatus(e: unknown): number | undefined {
  if (typeof e !== 'object' || e === null) return undefined;
  const h = e as MaybeHttpError;
  return typeof h.status === 'number' ? h.status : typeof h.statusCode === 'number' ? h.statusCode : undefined;
}

function readErrCode(e: unknown): string | undefined {
  if (typeof e !== 'object' || e === null) return undefined;
  const h = e as MaybeHttpError;
  return typeof h.code === 'string' ? h.code : undefined;
}

async function sleep(ms: number): Promise<void> {
  return new Promise((res) => setTimeout(res, ms));
}

export async function generate(args: GenerateArgs): Promise<GenerateResult> {
  const client = await getClient();
  // args.thinkingConfig (vision callers) overrides the derived 2.5/3.x split
  // when explicitly provided — e.g. gemini_ocr always wants a bare
  // `{ thinkingBudget: 0 }` regardless of the model-family branching in
  // buildThinkingConfig, since OCR is pinned to gemini-2.5-flash (see C6 in
  // gemini-client-ocr-helpers.ts).
  const thinkingConfig = args.thinkingConfig ?? buildThinkingConfig(args.model, args.thinking_budget);

  const config: Record<string, unknown> = {
    systemInstruction: args.system,
    temperature: args.temperature ?? 1.0,
    thinkingConfig,
  };
  if (typeof args.max_output_tokens === 'number') {
    // Gemini 2.5 counts thinking tokens against maxOutputTokens. Tight budgets
    // can leave zero room for visible text. Ensure at least ~1024 tokens of
    // output headroom beyond the thinking budget.
    const tb = args.thinking_budget;
    const minHeadroom = 1024;
    const minRequired = tb > 0 ? tb + minHeadroom : minHeadroom;
    config['maxOutputTokens'] = Math.max(args.max_output_tokens, minRequired);
  }
  if (args.response_mime_type) {
    config['responseMimeType'] = args.response_mime_type;
  }
  if (typeof args.topK === 'number') {
    config['topK'] = args.topK;
  }
  if (args.generationConfig?.mediaResolution) {
    config['mediaResolution'] = args.generationConfig.mediaResolution;
  }
  if (args.responseSchema !== undefined) {
    config['responseSchema'] = args.responseSchema;
  }

  const contents = args.parts ?? args.user;

  let attempt = 0;
  // eslint-disable-next-line no-constant-condition
  while (true) {
    attempt++;
    try {
      const resp = await client.models.generateContent({
        model: args.model,
        contents,
        config,
      });
      return normalizeResponse(resp);
    } catch (err) {
      const status = readHttpStatus(err);
      const code = readErrCode(err);
      const retryable = isRetryable(status, code);
      if (retryable && attempt < RETRY_MAX_ATTEMPTS) {
        const delay = RETRY_BASE_MS * Math.pow(RETRY_FACTOR, attempt - 1);
        await sleep(delay);
        continue;
      }
      const message = err instanceof Error ? err.message : String(err);
      const structured: StructuredError = retryable
        ? transient(`Gemini call failed after ${attempt} attempts: ${message}`, {
            status,
            code,
          })
        : apiError(`Gemini call failed: ${message}`, { status, code });
      throw structured as unknown as Error;
    }
  }
}

// ---------------------------------------------------------------------------
// Files API — upload/get/delete wrappers around @google/genai's `ai.files.*`
// (see gemini-client-ocr-helpers.ts's uploadViaFilesApi() for the
// upload+poll-until-ACTIVE orchestration that consumes these).
// ---------------------------------------------------------------------------

/** Normalized subset of the SDK's `types.File` we actually need. */
export interface GeminiFileHandle {
  /** Resource id (e.g. "files/abc123") — pass to get()/delete(). */
  name: string;
  uri: string;
  mimeType: string;
  state: string;
  errorMessage?: string;
}

interface RawFilesApiFile {
  name?: string;
  uri?: string;
  mimeType?: string;
  state?: string;
  error?: { message?: string };
}

function normalizeFileHandle(f: RawFilesApiFile): GeminiFileHandle {
  return {
    name: f.name ?? '',
    uri: f.uri ?? '',
    mimeType: f.mimeType ?? '',
    state: f.state ?? 'STATE_UNSPECIFIED',
    errorMessage: f.error?.message,
  };
}

/** Runs a Files API SDK call, mapping failures the same way generate()'s
 * retry loop does (5xx/429/network -> transient, everything else ->
 * api_error) — except a StructuredError raised earlier in the chain (e.g.
 * noCredentials() from getClient()) passes through unchanged. */
async function callFilesApi<T>(op: () => Promise<T>, verb: string): Promise<T> {
  try {
    return await op();
  } catch (err) {
    if (err && typeof err === 'object' && 'code' in err) throw err as unknown as Error;
    const status = readHttpStatus(err);
    const code = readErrCode(err);
    const retryable = isRetryable(status, code);
    const message = err instanceof Error ? err.message : String(err);
    const structured: StructuredError = retryable
      ? transient(`Gemini Files API ${verb} failed: ${message}`, { status, code })
      : apiError(`Gemini Files API ${verb} failed: ${message}`, { status, code });
    throw structured as unknown as Error;
  }
}

/** Uploads a local file to the Gemini Files API. Returns immediately with
 * whatever state the SDK reports (often PROCESSING for larger files) — the
 * caller (uploadViaFilesApi() in gemini-client-ocr-helpers.ts) polls
 * getFilesApiFile() until it reaches ACTIVE. */
export async function uploadFileToFilesApi(filePath: string, mimeType: string): Promise<GeminiFileHandle> {
  const client = await getClient();
  const file = await callFilesApi(
    () => client.files.upload({ file: filePath, config: { mimeType } }),
    'upload',
  );
  return normalizeFileHandle(file);
}

/** Retrieves the current state of a previously-uploaded file. */
export async function getFilesApiFile(name: string): Promise<GeminiFileHandle> {
  const client = await getClient();
  const file = await callFilesApi(() => client.files.get({ name }), 'get');
  return normalizeFileHandle(file);
}

/** Deletes a previously-uploaded file. Files persist ~48h server-side and
 * count against the user's storage quota, so callers should always delete
 * after use (success or failure) — see gemini_ocr.ts's cleanup try/finally. */
export async function deleteFilesApiFile(name: string): Promise<void> {
  const client = await getClient();
  await callFilesApi(() => client.files.delete({ name }), 'delete');
}

interface GenAiUsage {
  promptTokenCount?: number;
  candidatesTokenCount?: number;
  cachedContentTokenCount?: number;
}
interface GenAiCandidate {
  finishReason?: string;
}
interface GenAiResponse {
  text?: string;
  usageMetadata?: GenAiUsage;
  candidates?: GenAiCandidate[];
}

function normalizeResponse(resp: unknown): GenerateResult {
  const r = resp as GenAiResponse;
  const text = typeof r.text === 'string' ? r.text : '';
  const usage = r.usageMetadata ?? {};
  const finishReason =
    Array.isArray(r.candidates) && r.candidates[0]?.finishReason
      ? (r.candidates[0].finishReason as string)
      : 'STOP';
  return {
    text,
    finishReason,
    usage: {
      input_tokens: usage.promptTokenCount ?? 0,
      output_tokens: usage.candidatesTokenCount ?? 0,
      cached_tokens: usage.cachedContentTokenCount,
    },
  };
}
