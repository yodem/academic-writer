# npx Installer Design — Academic Writer Plugin

## Purpose
Reduce first-time setup friction for non-technical Humanities researchers. Current flow requires git knowledge and manual folder creation. Target: one command from any terminal, then open Claude.

## Users
Non-technical Humanities researchers using Claude Code on macOS/Windows.

## Success Criteria
- [ ] `npx academic-writer-setup` works from any empty directory (no clone required)
- [ ] All plugin files are copied to cwd automatically
- [ ] Interactive prompts (language, citation style, tools) complete without errors
- [ ] `profile.json` and required folders exist after setup
- [ ] Completion message clearly tells user their next step (open Claude, run /academic-writer-init)

## Constraints
- No extra runtime dependencies beyond `@clack/prompts` (already in package.json)
- Works offline (bundled template, no GitHub fetch at runtime)
- Node >= 18 (already enforced in engines field)

## Out of Scope
- Style fingerprinting (that's `/academic-writer-init` inside Claude — requires AI)
- Candlekeep/Vectorless installation (those are separate tools)
- Auto-commit or git init

## Approach Chosen
**Bundled template** — all plugin files ship inside the npm package in a `template/` directory. `setup.mjs` copies them to `process.cwd()` before running prompts. Works offline, zero extra dependencies.

## Architecture

```
npm package: academic-writer-setup
├── setup.mjs              ← CLI entrypoint (bin)
├── package.json           ← bin + files + engines
└── template/              ← all plugin files to copy
    ├── CLAUDE.md
    ├── words.txt
    └── .claude/
        ├── agents/
        │   ├── deep-reader.md
        │   ├── architect.md
        │   ├── section-writer.md
        │   ├── auditor.md
        │   └── synthesizer.md
        └── skills/
            ├── academic-writer/SKILL.md
            ├── academic-writer-init/SKILL.md
            ├── academic-writer-edit/SKILL.md
            ├── academic-writer-edit-section/SKILL.md
            ├── academic-writer-research/SKILL.md
            ├── academic-writer-health/SKILL.md
            ├── academic-writer-help/SKILL.md
            ├── academic-writer-update-field/SKILL.md
            └── academic-writer-update-tools/SKILL.md
```

## User Flow

```
1. npx academic-writer-setup
   ↓
2. Detect: is this a fresh directory or an existing install?
   ↓
3. Copy template/ → cwd (skip files that already exist in update mode)
   ↓
4. Interactive prompts (existing @clack/prompts flow):
   - Field of study
   - Article language
   - Citation style
   - Tool detection + selection
   ↓
5. Write .academic-writer/profile.json
   Create past-articles/, .cognetivy/runs/, .cognetivy/events/
   ↓
6. Completion message:
   "Drop 5–10 of your published papers in past-articles/,
    then open Claude Code in this folder and run /academic-writer-init"
```

## Data Flow
`setup.mjs` reads `__dirname/template/` → copies to `process.cwd()` → collects user answers → writes `profile.json`.

## Changes to Existing Code

### setup.mjs
Add at top of `main()`, before prompts:
1. Detect `fileURLToPath(import.meta.url)` → resolve `templateDir`
2. Copy `templateDir` → `cwd` recursively (using `fs.cpSync` with `recursive: true`, `force: false` for fresh install, `force: true` for update)
3. Check if `.academic-writer/profile.json` already exists to show "Update" vs "Fresh install" message

### package.json
Add `files` array to control what npm publishes:
```json
"files": ["setup.mjs", "template/"]
```

## Error Handling
- `cwd` not writable → show clear error, suggest running from a project folder
- Template file missing → warn and continue (graceful degradation per file)
- User cancels → `p.cancel()` + `process.exit(0)` (already handled)

## Testing Strategy
- Manual: run `npx .` from a temp directory, verify all files copied and profile created
- Smoke test: `node setup.mjs --dry-run` flag (optional) that lists what would be copied

## Questions Resolved
- Q: Should npx do style fingerprinting too?
  A: No — that requires AI. npx does the dumb interactive parts only.
- Q: Bundled vs GitHub download?
  A: Bundled — works offline, simpler, reliable.
- Q: GitHub clone vs npm publish?
  A: npm publish — only path where a non-technical user can do one-command install.
- Q: Where does friction currently live?
  A: Pre-Claude interactive setup (folder creation, profile) doesn't need AI and is better as a CLI.
