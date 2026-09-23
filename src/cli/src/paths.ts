import { resolve } from 'node:path';

let dataArgument: string | undefined;
let projectArgument: string | undefined;
export function setPathArguments(args: string[]): string[] {
  const rest: string[] = [];
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if ((arg === '--data-dir' || arg === '--project-dir') && args[index + 1]) {
      if (arg === '--data-dir') dataArgument = args[index + 1];
      else projectArgument = args[index + 1];
      index += 1;
    } else rest.push(arg);
  }
  return rest;
}
export function dataDir(): string { if (!dataArgument) throw new Error('ERROR: --data-dir is required'); return resolve(dataArgument); }
export function projectDir(): string { if (!projectArgument) throw new Error('ERROR: --project-dir is required'); return resolve(projectArgument); }
