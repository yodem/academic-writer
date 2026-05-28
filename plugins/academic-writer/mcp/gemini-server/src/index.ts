/**
 * academic-writer Gemini MCP server.
 *
 * Routes the plugin's reader-facing prose phases (drafting, synthesis, edits,
 * calibration samples) to Gemini. Claude Code spawns this server via the
 * plugin manifest; subagents inherit access to its tools.
 *
 * Five tools:
 *   - gemini_write_section
 *   - gemini_synthesize
 *   - gemini_edit
 *   - gemini_calibrate_sample
 *   - gemini_raw
 *
 * Auth, retry, calibration-bundle caching, and thinking-API split are handled
 * inside the bundled modules; the server itself is a thin adapter.
 */
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';

import { runWriteSection, WriteSectionInput } from './tools/write_section.js';
import { runSynthesize, SynthesizeInput } from './tools/synthesize.js';
import { runEdit, EditInput } from './tools/edit.js';
import { runCalibrateSample, CalibrateSampleInput } from './tools/calibrate_sample.js';
import { runRaw, RawInput } from './tools/raw.js';
import { isStructuredError } from './bundle.js';
import { resolveApiKey } from './gemini-client.js';
import { noCredentials, toToolResult, type StructuredError } from './errors.js';

/**
 * Wraps a tool handler:
 *   - checks credentials and returns no_credentials structured error if absent
 *   - catches StructuredError (no_credentials / api_error / transient / validation)
 *     and returns it as an isError MCP result
 *   - unexpected errors are mapped to api_error
 */
function wrap<T>(
  run: (input: unknown) => Promise<T>,
): (input: unknown) => Promise<{
  content: Array<{ type: 'text'; text: string }>;
  isError?: boolean;
}> {
  return async (input: unknown) => {
    const key = await resolveApiKey();
    if (!key) return toToolResult(noCredentials());
    try {
      const result = await run(input);
      return {
        content: [
          { type: 'text', text: JSON.stringify(result) },
        ],
      };
    } catch (err) {
      if (isStructuredError(err)) return toToolResult(err);
      const fallback: StructuredError = {
        code: 'api_error',
        message: err instanceof Error ? err.message : String(err),
      };
      return toToolResult(fallback);
    }
  };
}

async function main(): Promise<void> {
  const server = new McpServer({
    name: 'academic-writer-gemini',
    version: '0.1.0',
  });

  server.registerTool(
    'gemini_write_section',
    {
      description:
        'Draft a full article section (all paragraphs) via Gemini with built-in self-review against style fingerprint, language quality, anti-AI patterns, and repetition. Returns paragraphs with citations and self-review scores. Caller (section-writer) then runs the Claude citation auditor as a hard gate.',
      inputSchema: WriteSectionInput.shape,
    },
    wrap(runWriteSection),
  );

  server.registerTool(
    'gemini_synthesize',
    {
      description:
        'Cross-section polish pass over a full article draft. Improves transitions, removes cross-section repetition, smooths voice drift. Never touches citation strings or footnote markers.',
      inputSchema: SynthesizeInput.shape,
    },
    wrap(runSynthesize),
  );

  server.registerTool(
    'gemini_edit',
    {
      description:
        'Apply a single edit instruction to an existing passage in the researcher\'s voice. Preserves citations and quoted material verbatim.',
      inputSchema: EditInput.shape,
    },
    wrap(runEdit),
  );

  server.registerTool(
    'gemini_calibrate_sample',
    {
      description:
        'Produce one calibration paragraph from a topic brief for side-by-side voice comparison. Used by the voice-calibrator before approving Gemini for a new language.',
      inputSchema: CalibrateSampleInput.shape,
    },
    wrap(runCalibrateSample),
  );

  server.registerTool(
    'gemini_raw',
    {
      description:
        'Escape-hatch tool: send an arbitrary system+prompt to Gemini. Bypasses the calibration bundle. Intended for other plugins or one-off pings (e.g. /academic-writer:setup key test).',
      inputSchema: RawInput.shape,
    },
    wrap(runRaw),
  );

  const transport = new StdioServerTransport();
  await server.connect(transport);
}

// keep TS happy with unused z import for downstream extensions
void z;

main().catch((err: unknown) => {
  const msg = err instanceof Error ? err.message : String(err);
  // MCP stdio uses stdout for protocol; emit fatal-startup errors to stderr.
  process.stderr.write(`[gemini-mcp] fatal: ${msg}\n`);
  process.exit(1);
});
