# Academic Helper OrchestKit Plugin Refactor Plan

> **For Claude:** REQUIRED: Follow this plan task-by-task. Each task produces a verifiable output.
> **Design:** No separate design doc -- this plan IS the design (structural refactor, no new features).

**Goal:** Refactor Academic Helper from a flat `.claude/` plugin into a full OrchestKit-style marketplace plugin with `src/` -> `plugins/` build pipeline, TypeScript hooks, and skill-based setup (removing npx entirely).

**Architecture:** Source of truth lives in `src/` (agents, skills, hooks, settings). A build script (`scripts/build-plugins.sh`) compiles `src/` into `plugins/academic-writer/` which is the installable Claude Code plugin. Hooks are TypeScript compiled with esbuild into `dist/` bundles. The old npx installer (`setup.mjs`, `template/`) is replaced by a `/academic-writer:setup` skill.

**Tech Stack:** TypeScript (strict mode), esbuild, bash (build script), Node.js >= 20

**Prerequisites:** OrchestKit reference repo at `/Users/yotamfromm/dev/orchestkit/` for structural guidance

---

## Relevant Codebase Files

### OrchestKit Patterns to Follow
- `/Users/yotamfromm/dev/orchestkit/manifests/ork.json` - Plugin manifest format
- `/Users/yotamfromm/dev/orchestkit/.claude-plugin/marketplace.json` - Marketplace manifest
- `/Users/yotamfromm/dev/orchestkit/scripts/build-plugins.sh` - Build script (10 phases)
- `/Users/yotamfromm/dev/orchestkit/src/hooks/esbuild.config.mjs` - esbuild config with split bundles
- `/Users/yotamfromm/dev/orchestkit/src/hooks/bin/run-hook.mjs` - Hook runner CLI
- `/Users/yotamfromm/dev/orchestkit/src/hooks/hooks.json` - hooks.json format with `${CLAUDE_PLUGIN_ROOT}`
- `/Users/yotamfromm/dev/orchestkit/src/hooks/package.json` - Hooks package dependencies
- `/Users/yotamfromm/dev/orchestkit/src/hooks/tsconfig.json` - TS config (ES2022, strict, Bundler resolution)
- `/Users/yotamfromm/dev/orchestkit/src/settings/ork.settings.json` - Plugin settings format
- `/Users/yotamfromm/dev/orchestkit/package.json` - Root package with build scripts

### Current Academic Helper Files to Move/Transform
- `.claude/agents/*.md` (5 files) -> `src/agents/*.md` (copy as-is)
- `.claude/skills/academic-writer*/SKILL.md` (9 dirs) -> `src/skills/academic-writer*/SKILL.md` (copy as-is)
- `.claude/skills/cognetivy/SKILL.md` -> `src/skills/cognetivy/SKILL.md` (copy as-is)
- `hooks/hooks.json` -> `src/hooks/hooks.json` (rewrite for TypeScript runner)
- `hooks/scripts/check-profile.sh` -> `src/hooks/src/lifecycle/check-profile.ts` (convert)
- `hooks/scripts/load-fingerprint.sh` -> `src/hooks/src/lifecycle/load-fingerprint.ts` (convert)
- `words.txt` -> `src/words.txt` (move to src/)
- `CLAUDE.md` -> stays at root, update paths

### Files to DELETE
- `setup.mjs` - Replaced by `/academic-writer:setup` skill
- `setup.test.mjs` - No longer needed
- `template/` - No longer needed (plugin installs via marketplace)
- `hooks/` (root directory) - Replaced by `src/hooks/`
- `.claude/agents/` - Moved to `src/agents/`
- `.claude/skills/` - Moved to `src/skills/`

### Runtime Directories (unchanged, not part of plugin source)
- `.academic-writer/` - Profile data (created at runtime)
- `.cognetivy/` - Workflow state (created at runtime)
- `past-articles/` - Researcher's past work (local, gitignored)

---

## Target Directory Structure

```
Academic Helper/
├── src/                                 <- SOURCE (edit here!)
│   ├── agents/                          <- 5 agents (.md files with YAML frontmatter)
│   │   ├── deep-reader.md
│   │   ├── architect.md
│   │   ├── section-writer.md
│   │   ├── auditor.md
│   │   └── synthesizer.md
│   ├── skills/                          <- 10 skill directories
│   │   ├── academic-writer/SKILL.md
│   │   ├── academic-writer-init/SKILL.md
│   │   ├── academic-writer-edit/SKILL.md
│   │   ├── academic-writer-edit-section/SKILL.md
│   │   ├── academic-writer-research/SKILL.md
│   │   ├── academic-writer-health/SKILL.md
│   │   ├── academic-writer-help/SKILL.md
│   │   ├── academic-writer-update-field/SKILL.md
│   │   ├── academic-writer-update-tools/SKILL.md
│   │   ├── academic-writer-setup/SKILL.md   <- NEW (replaces setup.mjs)
│   │   └── cognetivy/SKILL.md
│   ├── settings/
│   │   └── academic-writer.settings.json    <- Plugin settings
│   ├── words.txt                            <- Hebrew linking words
│   └── hooks/                               <- TypeScript hooks system
│       ├── src/
│       │   ├── lifecycle/
│       │   │   ├── check-profile.ts         <- Converted from shell
│       │   │   └── load-fingerprint.ts      <- Converted from shell
│       │   ├── lib/
│       │   │   └── profile.ts               <- Shared profile utilities
│       │   ├── entries/
│       │   │   └── lifecycle.ts             <- Entry point for lifecycle bundle
│       │   ├── index.ts                     <- Unified entry
│       │   └── types.ts                     <- Type definitions
│       ├── dist/                            <- Compiled bundles (gitignored)
│       ├── bin/
│       │   └── run-hook.mjs                 <- Hook runner CLI
│       ├── hooks.json                       <- Hook definitions
│       ├── package.json
│       ├── esbuild.config.mjs
│       └── tsconfig.json
├── manifests/
│   └── academic-writer.json                 <- Plugin manifest
├── plugins/                                 <- GENERATED (never edit! gitignored)
│   └── academic-writer/                     <- Built plugin output
├── scripts/
│   └── build-plugins.sh                     <- Build script
├── .claude-plugin/
│   └── marketplace.json                     <- Plugin marketplace manifest
├── CLAUDE.md                                <- Updated for new paths
├── package.json                             <- Root package (build scripts)
├── .gitignore                               <- Updated
├── .academic-writer/                        <- Runtime (gitignored)
├── .cognetivy/                              <- Runtime (gitignored)
├── past-articles/                           <- Local (gitignored)
└── docs/                                    <- Plans & docs
```

---

## Phase 1: Scaffolding and File Migration

> **Exit Criteria:** All source files exist in `src/`, all build infrastructure files exist, `npm run build` succeeds (even if hooks aren't compiled yet).

### Task 1: Create src/ directory structure and move agents

**Files:**
- Create: `src/agents/` (directory)
- Move: `.claude/agents/deep-reader.md` -> `src/agents/deep-reader.md`
- Move: `.claude/agents/architect.md` -> `src/agents/architect.md`
- Move: `.claude/agents/section-writer.md` -> `src/agents/section-writer.md`
- Move: `.claude/agents/auditor.md` -> `src/agents/auditor.md`
- Move: `.claude/agents/synthesizer.md` -> `src/agents/synthesizer.md`

**Steps:**
1. Create `src/agents/` directory
2. Copy all 5 agent files from `.claude/agents/` to `src/agents/`
3. Verify all 5 files have YAML frontmatter (name, description, tools, model)
4. Do NOT delete `.claude/agents/` yet (Phase 4 cleanup)

**Verification:** `ls src/agents/*.md | wc -l` returns 5

### Task 2: Move skills to src/

**Files:**
- Create: `src/skills/` (directory with 10 subdirectories)
- Move: `.claude/skills/academic-writer*/SKILL.md` -> `src/skills/academic-writer*/SKILL.md`
- Move: `.claude/skills/cognetivy/SKILL.md` -> `src/skills/cognetivy/SKILL.md`

**Steps:**
1. Create `src/skills/` directory
2. Copy all 10 skill directories from `.claude/skills/` to `src/skills/`
3. Verify each directory contains a `SKILL.md` file
4. Do NOT delete `.claude/skills/` yet (Phase 4 cleanup)

**Verification:** `find src/skills -name SKILL.md | wc -l` returns 10

### Task 3: Move words.txt to src/

**Files:**
- Move: `words.txt` -> `src/words.txt`

**Steps:**
1. Copy `words.txt` to `src/words.txt`
2. Do NOT delete root `words.txt` yet (Phase 4 cleanup)

**Verification:** `diff words.txt src/words.txt` returns empty (identical)

### Task 4: Create plugin manifest

**Files:**
- Create: `manifests/academic-writer.json`

**Steps:**
1. Create `manifests/` directory
2. Write `manifests/academic-writer.json`:

```json
{
  "name": "academic-writer",
  "version": "0.2.0",
  "description": "AI-first academic writing assistant for Humanities researchers. Produces rigorously cited, style-matched academic articles as .docx files.",
  "author": {
    "name": "Yotam Fromm",
    "url": "https://github.com/yodem/academic-writer"
  },
  "homepage": "https://github.com/yodem/academic-writer",
  "repository": "https://github.com/yodem/academic-writer",
  "license": "MIT",
  "keywords": [
    "academic-writing",
    "humanities",
    "citations",
    "docx",
    "hebrew",
    "claude-code",
    "plugin"
  ],
  "skills": "all",
  "agents": "all",
  "hooks": "all"
}
```

**Verification:** `jq '.name' manifests/academic-writer.json` returns `"academic-writer"`

### Task 5: Create marketplace manifest

**Files:**
- Create: `.claude-plugin/marketplace.json`

**Steps:**
1. Create `.claude-plugin/` directory
2. Write `.claude-plugin/marketplace.json`:

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "academic-writer",
  "version": "0.2.0",
  "engine": ">=2.1.69",
  "description": "AI-first academic writing assistant for Humanities researchers. Produces rigorously cited, style-matched academic articles as .docx files.",
  "owner": {
    "name": "Yotam Fromm",
    "email": "yotam@example.com"
  },
  "metadata": {
    "description": "Academic writing plugin with 5 agents, 10+ skills, and TypeScript hooks for citation-verified article generation.",
    "pluginRoot": "./plugins"
  },
  "plugins": [
    {
      "name": "academic-writer",
      "description": "AI-first academic writing assistant — 5 agents, 10+ skills, TypeScript hooks for Humanities researchers.",
      "version": "0.2.0",
      "author": {
        "name": "Yotam Fromm",
        "email": "yotam@example.com"
      },
      "category": "writing",
      "source": "./plugins/academic-writer"
    }
  ]
}
```

**Verification:** `jq '.plugins[0].name' .claude-plugin/marketplace.json` returns `"academic-writer"`

### Task 6: Create plugin settings

**Files:**
- Create: `src/settings/academic-writer.settings.json`

**Steps:**
1. Create `src/settings/` directory
2. Write `src/settings/academic-writer.settings.json`:

```json
{
  "$schema": "https://claude.ai/schemas/plugin-settings.json",
  "respectGitignore": true,
  "env": {},
  "permissions": {
    "allow": [
      "Read",
      "Glob",
      "Grep"
    ],
    "deny": []
  }
}
```

**Verification:** `jq '.permissions.allow' src/settings/academic-writer.settings.json` returns array with 3 items

### Task 7: Create root package.json

**Files:**
- Modify: `package.json`

**Steps:**
1. Rewrite `package.json`:

```json
{
  "name": "academic-writer",
  "version": "0.2.0",
  "description": "AI-first academic writing assistant for Humanities researchers — Claude Code plugin",
  "scripts": {
    "build": "bash scripts/build-plugins.sh",
    "build:hooks": "cd src/hooks && npm run build",
    "typecheck": "cd src/hooks && npx tsc --noEmit",
    "clean": "rm -rf plugins/ src/hooks/dist/"
  },
  "repository": {
    "type": "git",
    "url": "https://github.com/yodem/academic-writer"
  },
  "keywords": [
    "claude-code",
    "plugin",
    "academic-writing",
    "humanities"
  ],
  "author": "Yotam Fromm",
  "license": "MIT",
  "engines": {
    "node": ">=20.0.0"
  }
}
```

**Verification:** `jq '.scripts.build' package.json` returns `"bash scripts/build-plugins.sh"`

### Task 8: Update .gitignore

**Files:**
- Modify: `.gitignore`

**Steps:**
1. Update `.gitignore` to include:

```
# Generated plugin output (never edit)
plugins/

# Hook build artifacts
src/hooks/dist/
src/hooks/node_modules/

# Runtime directories
.academic-writer/
.cognetivy/
past-articles/

# Node
node_modules/

# OS
.DS_Store

# Old files (remove after migration verified)
# setup.mjs
# setup.test.mjs
# template/
```

**Verification:** `grep -c 'plugins/' .gitignore` returns 1

---

## Phase 2: TypeScript Hooks System

> **Exit Criteria:** `cd src/hooks && npm install && npm run build` succeeds. Two hooks compiled: check-profile and load-fingerprint. `node bin/run-hook.mjs lifecycle/check-profile` runs without error.

### Task 9: Create hooks package.json

**Files:**
- Create: `src/hooks/package.json`

**Steps:**
1. Create `src/hooks/` directory structure: `src/`, `bin/`, `dist/`
2. Write `src/hooks/package.json`:

```json
{
  "name": "@academic-writer/hooks",
  "version": "1.0.0",
  "type": "module",
  "description": "TypeScript hooks for Academic Writer Claude Plugin",
  "main": "./dist/hooks.mjs",
  "bin": {
    "run-hook": "./bin/run-hook.mjs"
  },
  "scripts": {
    "build": "node esbuild.config.mjs",
    "typecheck": "tsc --noEmit",
    "clean": "rm -rf dist"
  },
  "engines": {
    "node": ">=20.0.0"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "esbuild": "^0.27.2",
    "typescript": "^5.6.0"
  },
  "license": "MIT"
}
```

**Verification:** `jq '.name' src/hooks/package.json` returns `"@academic-writer/hooks"`

### Task 10: Create hooks tsconfig.json

**Files:**
- Create: `src/hooks/tsconfig.json`

**Steps:**
1. Write `src/hooks/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "lib": ["ES2022"],
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "declaration": true,
    "declarationMap": true,
    "outDir": "./dist",
    "rootDir": "./src",
    "types": ["node"]
  },
  "include": ["src/**/*.ts"],
  "exclude": ["node_modules", "dist"]
}
```

**Verification:** File exists and is valid JSON

### Task 11: Create hook types

**Files:**
- Create: `src/hooks/src/types.ts`

**Steps:**
1. Write `src/hooks/src/types.ts` with Academic Writer specific types:

```typescript
/**
 * TypeScript type definitions for Academic Writer hooks
 * Based on Claude Code hook protocol (CC 2.1.69+)
 */

export type HookEvent =
  | 'SessionStart'
  | 'SessionEnd'
  | 'PreToolUse'
  | 'PostToolUse'
  | 'UserPromptSubmit'
  | 'Stop';

export interface HookInput {
  hook_event?: HookEvent;
  tool_name: string;
  session_id: string;
  tool_input: Record<string, unknown>;
  tool_output?: unknown;
  project_dir?: string;
  plugin_root?: string;
  prompt?: string;
}

export interface HookResult {
  continue: boolean;
  suppressOutput?: boolean;
  systemMessage?: string;
}

export interface ProfileData {
  fieldOfStudy: string;
  citationStyle: string;
  targetLanguage: string;
  styleFingerprint?: StyleFingerprint;
  tools?: Record<string, boolean>;
  articleStructure?: ArticleStructure;
  outputFormatPreferences?: OutputFormatPreferences;
}

export interface StyleFingerprint {
  sentenceLevel?: SentenceLevel;
  vocabularyAndRegister?: VocabularyAndRegister;
  paragraphStructure?: ParagraphStructure;
  toneAndVoice?: ToneAndVoice;
  transitions?: Transitions;
  citations?: Citations;
  rhetoricalPatterns?: RhetoricalPatterns;
  representativeExcerpts?: string[];
  // Legacy flat format fields
  averageSentenceLength?: string;
  vocabularyComplexity?: string;
  passiveVoiceFrequency?: string;
  paragraphStructure_legacy?: string;
  citationDensity?: string;
  toneDescriptors?: string[];
  preferredTransitions?: string[];
  sampleExcerpts?: string[];
}

interface SentenceLevel {
  averageLength?: string;
  structureVariety?: string;
  passiveVoice?: string;
}

interface VocabularyAndRegister {
  complexity?: string;
  registerLevel?: string;
  hebrewConventions?: string;
}

interface ParagraphStructure {
  pattern?: string;
  argumentProgression?: string;
}

interface ToneAndVoice {
  descriptors?: string[];
  authorStance?: string;
}

interface Transitions {
  preferred?: Record<string, string[]>;
}

interface Citations {
  density?: string;
  footnotesPerParagraph?: string;
  quoteLengthPreference?: string;
}

interface RhetoricalPatterns {
  common?: string[];
}

interface ArticleStructure {
  sections?: string[];
}

interface OutputFormatPreferences {
  font?: string;
  fontSize?: number;
  lineSpacing?: number;
}
```

**Verification:** `cd src/hooks && npx tsc --noEmit` passes

### Task 12: Create profile utility library

**Files:**
- Create: `src/hooks/src/lib/profile.ts`

**Steps:**
1. Write shared profile loading utility:

```typescript
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { ProfileData } from '../types.js';

const PROFILE_RELATIVE_PATH = '.academic-writer/profile.json';

export function getProfilePath(projectDir: string): string {
  return join(projectDir, PROFILE_RELATIVE_PATH);
}

export function loadProfile(projectDir: string): ProfileData | null {
  const profilePath = getProfilePath(projectDir);
  if (!existsSync(profilePath)) return null;
  try {
    const raw = readFileSync(profilePath, 'utf-8');
    return JSON.parse(raw) as ProfileData;
  } catch {
    return null;
  }
}
```

**Verification:** TypeScript compiles without errors

### Task 13: Convert check-profile.sh to TypeScript

**Files:**
- Create: `src/hooks/src/lifecycle/check-profile.ts`

**Steps:**
1. Convert the shell script logic to TypeScript:

```typescript
import type { HookInput, HookResult } from '../types.js';
import { getProfilePath } from '../lib/profile.js';
import { existsSync } from 'node:fs';

export function checkProfile(input: HookInput): HookResult {
  const projectDir = input.project_dir || process.env.CLAUDE_PROJECT_DIR || '.';
  const profilePath = getProfilePath(projectDir);

  if (!existsSync(profilePath)) {
    return {
      continue: true,
      systemMessage:
        'Academic Writer: No profile found. Run /academic-writer-init to get set up before writing your first article.',
    };
  }

  return { continue: true, suppressOutput: true };
}
```

**Verification:** TypeScript compiles without errors

### Task 14: Convert load-fingerprint.sh to TypeScript

**Files:**
- Create: `src/hooks/src/lifecycle/load-fingerprint.ts`

**Steps:**
1. Convert the Python-in-shell fingerprint loader to TypeScript:

```typescript
import type { HookInput, HookResult } from '../types.js';
import { loadProfile } from '../lib/profile.js';
import type { StyleFingerprint } from '../types.js';

export function loadFingerprint(input: HookInput): HookResult {
  const projectDir = input.project_dir || process.env.CLAUDE_PROJECT_DIR || '.';
  const profile = loadProfile(projectDir);

  if (!profile) {
    return { continue: true, suppressOutput: true };
  }

  const fp = profile.styleFingerprint;
  if (!fp) {
    return {
      continue: true,
      systemMessage:
        'Academic Writer: Profile exists but has no style fingerprint. Consider re-running /academic-writer-init.',
    };
  }

  const lines: string[] = [];
  lines.push('='.repeat(60));
  lines.push('ACADEMIC WRITER -- RESEARCHER PROFILE LOADED');
  lines.push('='.repeat(60));
  lines.push(`Field: ${profile.fieldOfStudy || 'Unknown'}`);
  lines.push(`Citation style: ${profile.citationStyle || 'Unknown'}`);
  lines.push('');

  if (fp.sentenceLevel && typeof fp.sentenceLevel === 'object') {
    formatExpandedFingerprint(fp, lines);
  } else {
    formatLegacyFingerprint(fp, lines);
  }

  lines.push('');
  lines.push('='.repeat(60));
  lines.push('This fingerprint is checked against every paragraph during writing.');
  lines.push('Update with /academic-writer-init (full) or edit .academic-writer/profile.json directly.');
  lines.push('='.repeat(60));

  return {
    continue: true,
    systemMessage: lines.join('\n'),
  };
}

function formatExpandedFingerprint(fp: StyleFingerprint, lines: string[]): void {
  const sl = fp.sentenceLevel;
  const vr = fp.vocabularyAndRegister;
  const ps = fp.paragraphStructure;
  const tv = fp.toneAndVoice;
  const tr = fp.transitions;
  const ci = fp.citations;
  const rp = fp.rhetoricalPatterns;

  lines.push('STYLE FINGERPRINT:');
  lines.push('-'.repeat(40));
  lines.push(`  Sentence length: ${sl?.averageLength ?? 'N/A'}`);
  lines.push(`  Structure variety: ${sl?.structureVariety ?? 'N/A'}`);
  lines.push(`  Passive voice: ${sl?.passiveVoice ?? 'N/A'}`);
  lines.push(`  Vocabulary: ${vr?.complexity ?? 'N/A'}`);
  lines.push(`  Register: ${vr?.registerLevel ?? 'N/A'}`);
  if (vr?.hebrewConventions) {
    lines.push(`  Hebrew conventions: ${vr.hebrewConventions}`);
  }
  lines.push(`  Paragraph pattern: ${ps?.pattern ?? 'N/A'}`);
  lines.push(`  Argument progression: ${ps?.argumentProgression ?? 'N/A'}`);
  lines.push(`  Tone: ${tv?.descriptors?.join(', ') || 'N/A'}`);
  lines.push(`  Author stance: ${tv?.authorStance ?? 'N/A'}`);
  lines.push(`  Citation density: ${ci?.density ?? 'N/A'} (~${ci?.footnotesPerParagraph ?? '?'}/paragraph)`);
  lines.push(`  Quote style: ${ci?.quoteLengthPreference ?? 'N/A'}`);
  if (rp?.common?.length) {
    lines.push(`  Rhetorical patterns: ${rp.common.join(', ')}`);
  }

  const pref = tr?.preferred;
  if (pref && Object.values(pref).some((v) => v?.length)) {
    lines.push('');
    lines.push('  Preferred transitions:');
    for (const [cat, phrases] of Object.entries(pref)) {
      if (phrases?.length) {
        lines.push(`    ${cat}: ${phrases.join(', ')}`);
      }
    }
  }

  const excerpts = fp.representativeExcerpts;
  if (excerpts?.length) {
    lines.push('');
    lines.push('  Representative excerpts (style targets):');
    for (let i = 0; i < Math.min(3, excerpts.length); i++) {
      const ex = excerpts[i];
      const display = ex.length > 150 ? ex.slice(0, 150) + '...' : ex;
      lines.push(`    ${i + 1}. "${display}"`);
    }
  }
}

function formatLegacyFingerprint(fp: StyleFingerprint, lines: string[]): void {
  lines.push('STYLE FINGERPRINT:');
  lines.push('-'.repeat(40));
  lines.push(`  Sentence length: ${fp.averageSentenceLength ?? 'N/A'} words`);
  lines.push(`  Vocabulary: ${fp.vocabularyComplexity ?? 'N/A'}`);
  lines.push(`  Passive voice: ${fp.passiveVoiceFrequency ?? 'N/A'}`);
  lines.push(`  Paragraph structure: ${fp.paragraphStructure_legacy ?? 'N/A'}`);
  lines.push(`  Citation density: ${fp.citationDensity ?? 'N/A'}`);
  if (fp.toneDescriptors?.length) {
    lines.push(`  Tone: ${fp.toneDescriptors.join(', ')}`);
  }
  if (fp.preferredTransitions?.length) {
    lines.push(`  Transitions: ${fp.preferredTransitions.slice(0, 8).join(', ')}`);
  }
  if (fp.sampleExcerpts?.length) {
    lines.push('');
    lines.push('  Representative excerpts:');
    for (let i = 0; i < Math.min(3, fp.sampleExcerpts.length); i++) {
      const ex = fp.sampleExcerpts[i];
      const display = ex.length > 150 ? ex.slice(0, 150) + '...' : ex;
      lines.push(`    ${i + 1}. "${display}"`);
    }
  }
}
```

**Verification:** TypeScript compiles without errors

### Task 15: Create lifecycle entry point and hook registry

**Files:**
- Create: `src/hooks/src/entries/lifecycle.ts`
- Create: `src/hooks/src/index.ts`

**Steps:**
1. Write `src/hooks/src/entries/lifecycle.ts`:

```typescript
import { checkProfile } from '../lifecycle/check-profile.js';
import { loadFingerprint } from '../lifecycle/load-fingerprint.js';

export const hooks: Record<string, (input: unknown) => unknown> = {
  'lifecycle/check-profile': checkProfile,
  'lifecycle/load-fingerprint': loadFingerprint,
};
```

2. Write `src/hooks/src/index.ts`:

```typescript
export { checkProfile } from './lifecycle/check-profile.js';
export { loadFingerprint } from './lifecycle/load-fingerprint.js';
export type { HookInput, HookResult, ProfileData, StyleFingerprint } from './types.js';
```

**Verification:** TypeScript compiles without errors

### Task 16: Create esbuild config

**Files:**
- Create: `src/hooks/esbuild.config.mjs`

**Steps:**
1. Write a simplified esbuild config (Academic Writer only needs lifecycle bundle):

```javascript
#!/usr/bin/env node
/**
 * esbuild configuration for Academic Writer hooks
 * Simplified from OrchestKit -- only lifecycle bundle needed
 */

import { build } from 'esbuild';
import { writeFileSync, mkdirSync } from 'node:fs';

const entryPoints = {
  lifecycle: './src/entries/lifecycle.ts',
};

const commonBuildOptions = {
  bundle: true,
  format: 'esm',
  platform: 'node',
  target: 'node20',
  minify: true,
  sourcemap: true,
  metafile: true,
  external: [],
};

async function main() {
  mkdirSync('./dist', { recursive: true });

  const startTime = Date.now();
  const stats = {
    generatedAt: new Date().toISOString(),
    buildTimeMs: 0,
    bundles: {},
    totalSize: 0,
  };

  console.log('Building Academic Writer hooks...\n');

  for (const [name, entryPoint] of Object.entries(entryPoints)) {
    const outfile = `./dist/${name}.mjs`;
    const result = await build({
      ...commonBuildOptions,
      entryPoints: [entryPoint],
      outfile,
      banner: {
        js: `// Academic Writer Hooks - ${name} bundle\n// Generated: ${new Date().toISOString()}\n`,
      },
    });

    const outputFile = result.metafile.outputs[`dist/${name}.mjs`];
    stats.bundles[name] = {
      size: outputFile.bytes,
      sizeKB: (outputFile.bytes / 1024).toFixed(2),
    };
    stats.totalSize += outputFile.bytes;

    console.log(`  ${name}.mjs: ${stats.bundles[name].sizeKB} KB`);
  }

  // Also build unified bundle
  const unifiedResult = await build({
    ...commonBuildOptions,
    entryPoints: ['./src/index.ts'],
    outfile: './dist/hooks.mjs',
    banner: {
      js: `// Academic Writer Hooks - Unified Bundle\n// Generated: ${new Date().toISOString()}\n`,
    },
  });

  const unifiedOutput = unifiedResult.metafile.outputs['dist/hooks.mjs'];
  stats.bundles['hooks'] = {
    size: unifiedOutput.bytes,
    sizeKB: (unifiedOutput.bytes / 1024).toFixed(2),
  };

  console.log(`\n  hooks.mjs (unified): ${stats.bundles['hooks'].sizeKB} KB`);

  stats.buildTimeMs = Date.now() - startTime;
  writeFileSync('./dist/bundle-stats.json', JSON.stringify(stats, null, 2));

  console.log(`\nBuild complete in ${stats.buildTimeMs}ms`);
}

main().catch((err) => {
  console.error('Build failed:', err);
  process.exit(1);
});
```

**Verification:** File is valid JavaScript

### Task 17: Create run-hook.mjs

**Files:**
- Create: `src/hooks/bin/run-hook.mjs`

**Steps:**
1. Write a simplified version of OrchestKit's run-hook.mjs adapted for Academic Writer (fewer bundles, simpler routing):

```javascript
#!/usr/bin/env node
/**
 * CLI Runner for Academic Writer TypeScript Hooks
 *
 * Usage: run-hook.mjs <hook-name>
 * Example: run-hook.mjs lifecycle/check-profile
 */

import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { existsSync } from 'node:fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const distDir = join(__dirname, '..', 'dist');
const pluginRoot = join(__dirname, '..', '..');

function getBundleName(hookName) {
  const prefix = hookName.split('/')[0];
  const bundleMap = {
    lifecycle: 'lifecycle',
  };
  return bundleMap[prefix] || null;
}

async function loadBundle(hookName) {
  const bundleName = getBundleName(hookName);
  if (!bundleName) return null;
  const bundlePath = join(distDir, `${bundleName}.mjs`);
  if (!existsSync(bundlePath)) return null;
  return await import(bundlePath);
}

function normalizeInput(input) {
  if (!input.tool_input && input.toolInput) {
    input.tool_input = input.toolInput;
  }
  if (!input.tool_input) {
    input.tool_input = {};
  }
  input.tool_name = input.tool_name || input.toolName || '';
  input.session_id = input.session_id || input.sessionId || process.env.CLAUDE_SESSION_ID || '';
  input.project_dir = input.project_dir || input.projectDir || process.env.CLAUDE_PROJECT_DIR || '.';
  input.plugin_root = pluginRoot;
  return input;
}

const hookName = process.argv[2];

if (!hookName) {
  console.log('{"continue":true,"suppressOutput":true}');
  process.exit(0);
}

let hooks;
try {
  hooks = await loadBundle(hookName);
} catch {
  console.log('{"continue":true,"suppressOutput":true}');
  process.exit(0);
}

if (!hooks) {
  console.log('{"continue":true,"suppressOutput":true}');
  process.exit(0);
}

const hookFn = hooks.hooks?.[hookName];

if (!hookFn) {
  console.log('{"continue":true,"suppressOutput":true}');
  process.exit(0);
}

let input = '';
let stdinClosed = false;

const timeout = setTimeout(() => {
  if (!stdinClosed) {
    stdinClosed = true;
    runHook(normalizeInput({}));
  }
}, 100);

process.stdin.setEncoding('utf8');

process.stdin.on('data', (chunk) => {
  clearTimeout(timeout);
  input += chunk;
});

process.stdin.on('end', () => {
  clearTimeout(timeout);
  if (!stdinClosed) {
    stdinClosed = true;
    try {
      const parsedInput = input.trim() ? JSON.parse(input) : {};
      runHook(normalizeInput(parsedInput));
    } catch (err) {
      console.log(JSON.stringify({
        continue: true,
        systemMessage: `Hook input parse error: ${err.message}`,
      }));
    }
  }
});

process.stdin.on('error', () => {
  clearTimeout(timeout);
  if (!stdinClosed) {
    stdinClosed = true;
    runHook(normalizeInput({}));
  }
});

async function runHook(parsedInput) {
  try {
    const result = await hookFn(parsedInput);
    console.log(JSON.stringify(result));
  } catch (err) {
    console.log(JSON.stringify({
      continue: true,
      systemMessage: `Hook error (${hookName}): ${err.message}`,
    }));
  }
}
```

**Verification:** `node src/hooks/bin/run-hook.mjs` outputs `{"continue":true,"suppressOutput":true}`

### Task 18: Create hooks.json for the plugin

**Files:**
- Create: `src/hooks/hooks.json`

**Steps:**
1. Write `src/hooks/hooks.json` using the TypeScript runner:

```json
{
  "description": "Academic Writer hooks -- profile and fingerprint checks (TypeScript/ESM)",
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node ${CLAUDE_PLUGIN_ROOT}/hooks/bin/run-hook.mjs lifecycle/check-profile",
            "timeout": 10,
            "statusMessage": "Checking researcher profile..."
          },
          {
            "type": "command",
            "command": "node ${CLAUDE_PLUGIN_ROOT}/hooks/bin/run-hook.mjs lifecycle/load-fingerprint",
            "timeout": 10,
            "statusMessage": "Loading style fingerprint..."
          }
        ]
      }
    ]
  }
}
```

**Verification:** `jq '.hooks.SessionStart' src/hooks/hooks.json` returns valid array

### Task 19: Install dependencies and build hooks

**Steps:**
1. `cd src/hooks && npm install`
2. `npm run build`
3. Verify `dist/lifecycle.mjs` exists
4. Verify `dist/hooks.mjs` exists
5. Test: `echo '{}' | node bin/run-hook.mjs lifecycle/check-profile` -- should output systemMessage about no profile
6. `npm run typecheck` -- should pass

**Verification:**
- `ls src/hooks/dist/lifecycle.mjs` exists
- `cd src/hooks && npm run typecheck` exits 0
- `echo '{}' | node src/hooks/bin/run-hook.mjs lifecycle/check-profile` returns JSON with systemMessage

---

## Phase 3: Build Script and Plugin Assembly

> **Exit Criteria:** `npm run build` produces `plugins/academic-writer/` with all skills, agents, hooks, and a valid `.claude-plugin/plugin.json`.

### Task 20: Create build script

**Files:**
- Create: `scripts/build-plugins.sh`

**Steps:**
1. Create `scripts/` directory
2. Write `scripts/build-plugins.sh` -- a simplified version of OrchestKit's script:

```bash
#!/usr/bin/env bash
# Academic Writer Plugin Build Script
# Assembles plugin from source files and manifest.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$PROJECT_ROOT/src"
MANIFESTS_DIR="$PROJECT_ROOT/manifests"
PLUGINS_DIR="$PROJECT_ROOT/plugins"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  Academic Writer Plugin Build${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# Phase 1: Validate
echo -e "${BLUE}[1/6] Validating environment...${NC}"
[[ ! -d "$SRC_DIR" ]] && echo -e "${RED}Error: src/ not found${NC}" && exit 1
[[ ! -d "$MANIFESTS_DIR" ]] && echo -e "${RED}Error: manifests/ not found${NC}" && exit 1
command -v jq &>/dev/null || { echo -e "${RED}Error: jq required${NC}"; exit 1; }
echo -e "${GREEN}  Environment OK${NC}"

# Phase 2: Build hooks
echo -e "${BLUE}[2/6] Building TypeScript hooks...${NC}"
if [[ -f "$SRC_DIR/hooks/package.json" ]]; then
  cd "$SRC_DIR/hooks"
  [[ ! -d "node_modules" ]] && npm install --silent
  npm run build
  cd "$PROJECT_ROOT"
  echo -e "${GREEN}  Hooks built${NC}"
else
  echo -e "${RED}  No hooks package.json found${NC}"
  exit 1
fi

# Phase 3: Clean previous build
echo -e "${BLUE}[3/6] Cleaning previous build...${NC}"
if [[ -d "$PLUGINS_DIR" ]]; then
  find "$PLUGINS_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true
fi
mkdir -p "$PLUGINS_DIR"
echo -e "${GREEN}  Cleaned${NC}"

# Phase 4: Build plugin from manifest
echo -e "${BLUE}[4/6] Building plugin...${NC}"
for manifest in "$MANIFESTS_DIR"/*.json; do
  [[ ! -f "$manifest" ]] && continue

  PLUGIN_NAME=$(jq -r '.name' "$manifest")
  PLUGIN_VERSION=$(jq -r '.version' "$manifest")
  PLUGIN_DESC=$(jq -r '.description' "$manifest")

  PLUGIN_DIR="$PLUGINS_DIR/$PLUGIN_NAME"
  mkdir -p "$PLUGIN_DIR/.claude-plugin"

  # Copy skills
  cp -R "$SRC_DIR/skills" "$PLUGIN_DIR/"
  skill_count=$(find "$PLUGIN_DIR/skills" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')

  # Copy agents
  cp -R "$SRC_DIR/agents" "$PLUGIN_DIR/"
  agent_count=$(find "$PLUGIN_DIR/agents" -name "*.md" | wc -l | tr -d ' ')

  # Copy settings
  SETTINGS_FILE="$SRC_DIR/settings/${PLUGIN_NAME}.settings.json"
  if [[ -f "$SETTINGS_FILE" ]]; then
    cp "$SETTINGS_FILE" "$PLUGIN_DIR/settings.json"
  fi

  # Copy hooks (exclude node_modules and src)
  rsync -a \
    --exclude='node_modules' \
    --exclude='src' \
    --exclude='.gitignore' \
    --exclude='package-lock.json' \
    --exclude='tsconfig.json' \
    --exclude='esbuild.config.mjs' \
    "$SRC_DIR/hooks/" "$PLUGIN_DIR/hooks/"

  # Copy shared resources (words.txt)
  if [[ -f "$SRC_DIR/words.txt" ]]; then
    cp "$SRC_DIR/words.txt" "$PLUGIN_DIR/"
  fi

  # Generate plugin.json
  jq -n \
    --arg name "$PLUGIN_NAME" \
    --arg version "$PLUGIN_VERSION" \
    --arg desc "$PLUGIN_DESC" \
    '{
      name: $name,
      version: $version,
      description: $desc,
      author: {
        name: "Yotam Fromm",
        url: "https://github.com/yodem/academic-writer"
      },
      homepage: "https://github.com/yodem/academic-writer",
      repository: "https://github.com/yodem/academic-writer",
      license: "MIT",
      keywords: ["academic-writing","humanities","citations","claude-code","plugin"],
      skills: "./skills/",
      commands: "./commands/"
    }' > "$PLUGIN_DIR/.claude-plugin/plugin.json"

  # Generate commands from user-invocable skills (CC bug workaround)
  if [[ -d "$PLUGIN_DIR/skills" ]]; then
    for skill_md in "$PLUGIN_DIR/skills"/*/SKILL.md; do
      [[ ! -f "$skill_md" ]] && continue
      if grep -q "^user-invocable: *true" "$skill_md"; then
        skill_name=$(dirname "$skill_md" | xargs basename)
        mkdir -p "$PLUGIN_DIR/commands"
        # Extract frontmatter fields and generate command file
        frontmatter=$(sed -n '2,/^---$/p' "$skill_md" | sed '$d')
        description=$(echo "$frontmatter" | grep -E "^description:" | sed 's/^description: *//')
        allowed_tools=$(echo "$frontmatter" | grep -E "^allowed-tools:" | sed 's/^allowed-tools: *//')
        [[ -z "$allowed_tools" ]] && allowed_tools="[Bash, Read, Write, Edit, Glob, Grep]"
        {
          echo "---"
          echo "description: $description"
          echo "allowed-tools: $allowed_tools"
          echo "---"
          echo ""
          echo "# Auto-generated from skills/$skill_name/SKILL.md"
          echo ""
          awk 'BEGIN{c=0} /^---$/{c++; next} c>=2{print}' "$skill_md"
        } > "$PLUGIN_DIR/commands/$skill_name.md"
      fi
    done
  fi

  command_count=$(find "$PLUGIN_DIR/commands" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')

  echo -e "${GREEN}  Built $PLUGIN_NAME: $skill_count skills, $agent_count agents, $command_count commands${NC}"
done

# Phase 5: Validate
echo -e "${BLUE}[5/6] Validating...${NC}"
for plugin_dir in "$PLUGINS_DIR"/*; do
  [[ ! -d "$plugin_dir" ]] && continue
  plugin_name=$(basename "$plugin_dir")
  if [[ ! -f "$plugin_dir/.claude-plugin/plugin.json" ]]; then
    echo -e "${RED}  $plugin_name: Missing plugin.json${NC}" && exit 1
  fi
  if ! jq empty "$plugin_dir/.claude-plugin/plugin.json" 2>/dev/null; then
    echo -e "${RED}  $plugin_name: Invalid JSON${NC}" && exit 1
  fi
done
echo -e "${GREEN}  Validation passed${NC}"

# Phase 6: Summary
echo -e "${BLUE}[6/6] Summary${NC}"
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  BUILD COMPLETE${NC}"
echo -e "${CYAN}============================================${NC}"
echo -e "  Output: ${GREEN}$PLUGINS_DIR${NC}"
```

3. `chmod +x scripts/build-plugins.sh`

**Verification:** `npm run build` completes with exit code 0

### Task 21: Verify built plugin structure

**Steps:**
1. Run `npm run build`
2. Verify `plugins/academic-writer/.claude-plugin/plugin.json` exists and is valid JSON
3. Verify `plugins/academic-writer/skills/` has 10+ skill directories
4. Verify `plugins/academic-writer/agents/` has 5 agent files
5. Verify `plugins/academic-writer/hooks/bin/run-hook.mjs` exists
6. Verify `plugins/academic-writer/hooks/dist/lifecycle.mjs` exists
7. Verify `plugins/academic-writer/hooks/hooks.json` exists
8. Verify `plugins/academic-writer/words.txt` exists

**Verification:** All 8 checks pass

---

## Phase 4: Setup Skill and CLAUDE.md Update

> **Exit Criteria:** `/academic-writer:setup` skill exists, CLAUDE.md references new paths, old files (setup.mjs, template/, root hooks/) deleted.

### Task 22: Create /academic-writer:setup skill

**Files:**
- Create: `src/skills/academic-writer-setup/SKILL.md`

**Steps:**
1. Write the setup skill that replaces the npx installer. This skill handles:
   - Checking for existing profile
   - Asking field of study
   - Asking target language
   - Detecting available integrations (Candlekeep, Vectorless, MongoDB, Cognetivy)
   - Creating `.academic-writer/profile.json`
   - Analyzing past articles for style fingerprint

The skill content should include frontmatter:
```yaml
---
name: academic-writer-setup
description: First-time setup for Academic Writer -- creates researcher profile, detects integrations, analyzes writing style
user-invocable: true
allowed-tools: [Bash, Read, Write, Glob, Grep]
---
```

And instructions that mirror what `setup.mjs` does but as an interactive Claude conversation:
- Ask the researcher their field of study
- Ask target language (default Hebrew)
- Ask citation style (default inline-parenthetical)
- Auto-detect integrations: check if `ck` CLI exists, if Vectorless is running, if `cognetivy` CLI exists
- Create `.academic-writer/` directory and `profile.json`
- If `past-articles/` has files, analyze them for style fingerprint
- [CHECKPOINT] Whether to auto-index sources with Candlekeep (if available)

**Verification:** `cat src/skills/academic-writer-setup/SKILL.md | head -5` shows valid YAML frontmatter

### Task 23: Update CLAUDE.md for new paths

**Files:**
- Modify: `CLAUDE.md`

**Steps:**
1. Update the CLAUDE.md to reflect the new plugin architecture:
   - Change "Slash Commands" table: add `/academic-writer-setup`
   - Update "Agent Architecture" table: paths now say `src/agents/` (development) and `plugins/academic-writer/agents/` (runtime)
   - Add "Build System" section explaining `npm run build` and `src/` -> `plugins/` flow
   - Update any path references from `.claude/agents/` to the plugin structure
   - Keep all functionality descriptions identical

Key sections to update:
- Add note: "Development: edit files in `src/`. Run `npm run build` to assemble plugin."
- Update slash commands table to include `/academic-writer-setup`
- Add build instructions section

**Verification:** `grep 'npm run build' CLAUDE.md` returns at least 1 match

### Task 24: Delete old files

**Files:**
- Delete: `setup.mjs`
- Delete: `setup.test.mjs`
- Delete: `template/` (entire directory)
- Delete: `hooks/` (root-level duplicate)
- Delete: `.claude/agents/` (moved to `src/agents/`)
- Delete: `.claude/skills/` (moved to `src/skills/`)
- Delete: root `words.txt` (moved to `src/words.txt`)

**Steps:**
1. Remove each file/directory listed above
2. Remove `@clack/prompts` dependency (no longer needed)
3. Remove `node_modules/` if it exists at root level

**IMPORTANT:** Before deleting, verify the src/ copies exist:
- `ls src/agents/*.md | wc -l` must return 5
- `find src/skills -name SKILL.md | wc -l` must return >= 10
- `test -f src/words.txt` must succeed
- `test -f src/hooks/hooks.json` must succeed

**Verification:** `test ! -f setup.mjs && test ! -d template/ && test ! -d hooks/` all succeed

### Task 25: Final build and verification

**Steps:**
1. Run `npm run build`
2. Verify `plugins/academic-writer/` is complete:
   - `.claude-plugin/plugin.json` valid
   - `skills/` has 11 directories (10 original + setup)
   - `agents/` has 5 .md files
   - `hooks/dist/lifecycle.mjs` exists
   - `hooks/hooks.json` exists
   - `hooks/bin/run-hook.mjs` exists
   - `words.txt` exists
3. Verify TypeScript compiles: `cd src/hooks && npm run typecheck`
4. Test hook runner: `echo '{}' | node src/hooks/bin/run-hook.mjs lifecycle/check-profile`

**Verification:** All checks pass. Commit the refactor.

---

## Risks

| Risk | P (1-5) | I (1-5) | Score | Mitigation |
|------|---------|---------|-------|------------|
| OrchestKit hooks break existing ork plugin | 2 | 4 | 8 | Academic Writer hooks use separate plugin root, no interference |
| `${CLAUDE_PLUGIN_ROOT}` not resolving for hooks | 3 | 4 | 12 | Test with Claude Code immediately after build; fallback to absolute paths |
| Skills lose `user-invocable: true` during copy | 2 | 3 | 6 | Build script validates frontmatter presence |
| Profile paths break (hooks expect relative `.academic-writer/`) | 2 | 4 | 8 | Hooks use `project_dir` from input for absolute path resolution |
| Build script fails on Linux (macOS-specific commands) | 1 | 2 | 2 | Using POSIX-compatible commands (bash, jq, rsync) |
| Missing jq dependency on researcher's machine | 2 | 3 | 6 | Add jq check at build start with install instructions |

---

## Success Criteria

- [ ] `npm run build` produces complete `plugins/academic-writer/` directory
- [ ] `cd src/hooks && npm run typecheck` passes
- [ ] Hook runner works: `echo '{}' | node src/hooks/bin/run-hook.mjs lifecycle/check-profile`
- [ ] All 5 agents present in built plugin
- [ ] All 11 skills present in built plugin (9 original + cognetivy + setup)
- [ ] `setup.mjs`, `template/`, root `hooks/` all removed
- [ ] `CLAUDE.md` updated with build instructions
- [ ] `.claude-plugin/marketplace.json` exists and is valid
- [ ] `manifests/academic-writer.json` exists and is valid
- [ ] `.gitignore` excludes `plugins/` and `src/hooks/dist/`
