import { spawn } from 'node:child_process';
import { basename, dirname, join, resolve } from 'node:path';
import thresholds from '../../thresholds.json' with { type: 'json' };

export type PiUsage = { in: number; out: number };
export type PiResult = { finalText: string; usage: PiUsage };
export type PiRunner = (args: string[], systemPrompt: string) => Promise<PiResult>;

const spawnRunner: PiRunner = async (args, systemPrompt) => {
  // `pi --system-prompt` takes the prompt TEXT (pi --help), not a file path.
  const fullArgs = args.map((arg) => arg === '__SYSTEM_PROMPT__' ? systemPrompt : arg);
  return await new Promise<PiResult>((resolve, reject) => {
    const child = spawn('pi', fullArgs, { stdio: ['pipe', 'pipe', 'pipe'] });
    child.stdin.end();
    let stdout = '';
    let stderr = '';
    child.stdout.setEncoding('utf8').on('data', (chunk: string) => { stdout += chunk; });
    child.stderr.setEncoding('utf8').on('data', (chunk: string) => { stderr += chunk; });
    child.on('error', reject);
    child.on('close', (code) => {
      try {
        if (code !== 0) { reject(new Error(stderr || `pi exited ${String(code)}`)); return; }
        const events = stdout.split('\n').filter(Boolean).map((line) => JSON.parse(line) as Record<string, unknown>);
        const final = events.filter((event) => event.type === 'message_end').at(-1);
        const message = final?.message as { content?: Array<{ text?: string }>; usage?: { input?: number; output?: number } } | undefined;
        if (!message) { reject(new Error('missing final message_end event')); return; }
        const finalText = (message.content ?? []).map((item) => item.text ?? '').join('');
        resolve({ finalText, usage: { in: message.usage?.input ?? 0, out: message.usage?.output ?? 0 } });
      } catch (error) { reject(error); }
    });
  });
};

let runner = spawnRunner;
let readyOverride: boolean | undefined;
export function __setPiRunner(value: PiRunner): void { runner = value; }
export function __setPiReady(value: boolean | undefined): void { readyOverride = value; }
export async function piReady(): Promise<boolean> {
  if (readyOverride !== undefined) return readyOverride;
  return await new Promise((resolve) => {
    const child = spawn('pi', ['auth', 'check', '--provider', 'openrouter'], { stdio: 'ignore' });
    child.on('error', () => resolve(false));
    child.on('close', (code) => resolve(code === 0));
  });
}
export async function callPi(step: string, prompt: string, systemPrompt: string): Promise<PiResult> {
  const model = piModelFor(step);
  const args = ['-p', '--mode', 'json', '--no-session', '--no-tools', '--no-extensions', '--no-skills', '--no-context-files', '--no-prompt-templates', '--provider', 'openrouter', '--model', model, '--system-prompt', '__SYSTEM_PROMPT__', '--skill', join(pluginRoot(), 'pi-skills', 'aw-judge'), prompt];
  return await runner(args, systemPrompt);
}
export function piModelFor(step: string): string {
  const modelTable = thresholds.models as Record<string, { piModel?: string }>;
  const model = modelTable[step]?.piModel;
  if (!model) throw new Error(`ERROR ${step}: no Pi model configured`);
  return model;
}

// Bash subprocesses get no CLAUDE_PLUGIN_ROOT (docs/refactor/runtime-facts.md): derive it from
// this binary's location, <root>/bin/aw.
export function pluginRoot(argv1: string = process.argv[1] ?? ''): string {
  const bin = dirname(resolve(argv1));
  if (basename(bin) === 'bin') return dirname(bin);
  const env = (process.env.CLAUDE_PLUGIN_ROOT ?? '').trim();
  if (env) return env;
  throw new Error('ERROR pi: cannot locate the plugin root (run aw from <plugin>/bin/aw)');
}
