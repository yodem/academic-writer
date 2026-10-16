import { runCommand, splitCommand } from '../exec.ts';
import { LibraryError } from '../types.ts';
import { evalLimits } from './limits.ts';
import type { EvalIo, Route } from './types.ts';

/** The command that runs `aw` itself: AW_EVAL_AW_COMMAND, else io.awCommand, else this program's entry file. */
export function awCommandFor(io: EvalIo, env: NodeJS.ProcessEnv): string[] {
  const fromEnv = env.AW_EVAL_AW_COMMAND?.trim();
  if (fromEnv) return splitCommand(fromEnv);
  if (io.awCommand && io.awCommand.length > 0) return io.awCommand;
  const entry = process.argv[1];
  if (!entry) throw new LibraryError('config', 'ERROR library eval: cannot tell how to run aw; set AW_EVAL_AW_COMMAND');
  return [process.execPath, entry];
}

export type AwCall = { args: string[]; route: Route; run?: string; claim?: string };
export type AwRunner = (call: AwCall) => Promise<string>;

/**
 * `aw --project-dir <project> library <args>` with the route forced (AW_LIBRARY_ROUTE) so the answer comes from one
 * library only and nothing is shadowed. Returns stdout. The timeout is the library's own readAll limit.
 */
export function makeAwRunner(project: string, command: string[], env: NodeJS.ProcessEnv): AwRunner {
  return ({ args, route, run, claim }) => runCommand(command, [
    '--project-dir', project, 'library', ...args, ...(run ? ['--run', run] : []), ...(claim ? ['--claim', claim] : []),
  ], {
    timeoutMs: evalLimits.timeoutMs.readAll,
    maxBuffer: evalLimits.maxBufferBytes,
    env: { ...env, AW_LIBRARY_ROUTE: route },
  });
}
