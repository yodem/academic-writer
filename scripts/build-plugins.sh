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
echo -e "${BLUE}[1/7] Validating environment...${NC}"
[[ ! -d "$SRC_DIR" ]] && echo -e "${RED}Error: src/ not found${NC}" && exit 1
[[ ! -d "$MANIFESTS_DIR" ]] && echo -e "${RED}Error: manifests/ not found${NC}" && exit 1
command -v jq &>/dev/null || { echo -e "${RED}Error: jq required. Install with: brew install jq${NC}"; exit 1; }
echo -e "${GREEN}  Environment OK${NC}"

# Phase 2: Build hooks
echo -e "${BLUE}[2/7] Building TypeScript hooks...${NC}"
if [[ -f "$SRC_DIR/hooks/package.json" ]]; then
  cd "$SRC_DIR/hooks"
  [[ ! -d "node_modules" ]] && npm install --silent
  npm run build 2>&1 | sed 's/^/  /'
  cd "$PROJECT_ROOT"
  echo -e "${GREEN}  Hooks built${NC}"
else
  echo -e "${RED}  No hooks package.json found${NC}"
  exit 1
fi

# Phase 3: Clean previous build. Do not copy mcp/ into the built plugin. Preserve the legacy
# server source subtree until the T15a/T15b integration lead confirms it has been moved.
echo -e "${BLUE}[3/7] Cleaning previous build...${NC}"
if [[ -d "$PLUGINS_DIR" ]]; then
  for plugin_dir in "$PLUGINS_DIR"/*; do
    [[ ! -d "$plugin_dir" ]] && continue
    find "$plugin_dir" -mindepth 1 -maxdepth 1 ! -name mcp -exec rm -rf {} + 2>/dev/null || true
  done
fi
mkdir -p "$PLUGINS_DIR"
echo -e "${GREEN}  Cleaned${NC}"

# Phase 4: Build plugin from manifest
echo -e "${BLUE}[4/7] Building plugin...${NC}"
for manifest in "$MANIFESTS_DIR"/*.json; do
  [[ ! -f "$manifest" ]] && continue

  PLUGIN_NAME=$(jq -r '.name' "$manifest")
  PLUGIN_VERSION=$(jq -r '.version' "$manifest")
  PLUGIN_DESC=$(jq -r '.description' "$manifest")

  PLUGIN_DIR="$PLUGINS_DIR/$PLUGIN_NAME"
  mkdir -p "$PLUGIN_DIR/.claude-plugin"

  # Regenerate the command lists in the HTML guide and the help skill from skill
  # frontmatter (and stamp the version), so they can never drift from the skills.
  python3 "$PROJECT_ROOT/scripts/gen-guide.py"

  # Copy skills
  if [[ -d "$SRC_DIR/skills" ]]; then
    cp -R "$SRC_DIR/skills" "$PLUGIN_DIR/"
  fi
  # Ship the offline HTML guide opened by /academic-writer:intro.
  if [[ -d "$SRC_DIR/guide" ]]; then
    cp -R "$SRC_DIR/guide" "$PLUGIN_DIR/"
  fi
  # Ship canonical JSON schemas beside the runtime scripts for gate.py.
  if [[ -d "$SRC_DIR/schemas" ]]; then
    cp -R "$SRC_DIR/schemas" "$PLUGIN_DIR/"
  fi
  skill_count=$(find "$PLUGIN_DIR/skills" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')

  # Copy Pi judge skills as a separate Pi skill directory.
  if [[ -d "$SRC_DIR/pi-skills" ]]; then
    cp -R "$SRC_DIR/pi-skills" "$PLUGIN_DIR/"
  fi

  # Copy agents
  if [[ -d "$SRC_DIR/agents" ]]; then
    mkdir -p "$PLUGIN_DIR/agents"
    # Copy agent definitions only. src/agents/memory/ is local, gitignored agent memory:
    # anything under agents/ is loaded by Claude Code as an agent, so memory there
    # creates phantom frontmatter-less agents (claude plugin validate, 2026-09-23).
    find "$SRC_DIR/agents" -maxdepth 1 -name '*.md' -exec cp {} "$PLUGIN_DIR/agents/" \;
  fi
  agent_count=$(find "$PLUGIN_DIR/agents" -maxdepth 1 -name "*.md" 2>/dev/null | wc -l | tr -d ' ')

  # Copy settings
  SETTINGS_FILE="$SRC_DIR/settings/${PLUGIN_NAME}.settings.json"
  if [[ -f "$SETTINGS_FILE" ]]; then
    cp "$SETTINGS_FILE" "$PLUGIN_DIR/settings.json"
  fi

  # Copy hooks (exclude node_modules, src, and build config)
  if [[ -d "$SRC_DIR/hooks" ]]; then
    mkdir -p "$PLUGIN_DIR/hooks"
    # Copy only runtime files: bin/, dist/, hooks.json, package.json
    [[ -d "$SRC_DIR/hooks/bin" ]] && cp -R "$SRC_DIR/hooks/bin" "$PLUGIN_DIR/hooks/"
    [[ -d "$SRC_DIR/hooks/dist" ]] && cp -R "$SRC_DIR/hooks/dist" "$PLUGIN_DIR/hooks/"
    [[ -f "$SRC_DIR/hooks/hooks.json" ]] && cp "$SRC_DIR/hooks/hooks.json" "$PLUGIN_DIR/hooks/"
    [[ -f "$SRC_DIR/hooks/package.json" ]] && cp "$SRC_DIR/hooks/package.json" "$PLUGIN_DIR/hooks/"
  fi

  # Copy scripts
  if [[ -d "$SRC_DIR/scripts" ]]; then
    cp -R "$SRC_DIR/scripts" "$PLUGIN_DIR/"
  fi

  # Copy workflow scripts (Workflow-tool scriptPath targets)
  if [[ -d "$SRC_DIR/workflows" ]]; then
    cp -R "$SRC_DIR/workflows" "$PLUGIN_DIR/"
  fi

  # Copy shared resources (per-language linking-words references)
  for words_file in "$SRC_DIR"/words-*.md; do
    [[ -f "$words_file" ]] && cp "$words_file" "$PLUGIN_DIR/"
  done

  # Copy thresholds
  if [[ -f "$SRC_DIR/thresholds.json" ]]; then
    cp "$SRC_DIR/thresholds.json" "$PLUGIN_DIR/"
  fi

  # Generate plugin.json — read recognized plugin.json fields FROM the manifest.
  # Only the schema-recognized keys are emitted (Official Docs p.114):
  #   name, version, description, author, homepage, repository, license, keywords, userConfig.
  # No mcpServers block — the bundled Gemini MCP server was retired; its tools now live in
  # the `aw` CLI (src/cli/), invoked from skills via Bash, not registered as an MCP server.
  # userConfig is copied through verbatim so Claude Code prompts for (and securely
  # stores) declared options like the Gemini API key at plugin-enable time.
  # author/homepage/repository/license/keywords fall back to defaults only when absent.
  jq '{
    name: .name,
    version: .version,
    description: .description,
    author: (.author // { name: "Yotam Fromm", url: "https://github.com/yodem/academic-writer" }),
    homepage: (.homepage // "https://github.com/yodem/academic-writer"),
    repository: (.repository // "https://github.com/yodem/academic-writer"),
    license: (.license // "MIT"),
    keywords: (.keywords // ["academic-writing","humanities","citations","claude-code","plugin"])
  }
  + (if .userConfig then { userConfig: .userConfig } else {} end)' \
    "$manifest" > "$PLUGIN_DIR/.claude-plugin/plugin.json"

  # Commands are deliberately NOT generated from skills. Claude Code registers
  # user-invocable skills in the palette on its own; shipping a commands/<name>.md
  # wrapper alongside made every such skill appear three times in the palette.
  # See CHANGELOG. Do not reintroduce a commands/ generator here.

  echo -e "${GREEN}  Built $PLUGIN_NAME v$PLUGIN_VERSION: $skill_count skills, $agent_count agents${NC}"
done

# Phase 5: Build the standalone academic-writer CLI (`aw`). Its tools (draft, synthesize,
# edit, ocr, evidence, proofread, decide, voice, revise, ...) replace the retired bundled
# Gemini MCP server; skills invoke the built binary via Bash, not an MCP connection.
echo -e "${BLUE}[5/7] Building aw CLI...${NC}"
if [[ -f "$SRC_DIR/cli/package.json" ]]; then
  cd "$SRC_DIR/cli"
  [[ -d node_modules ]] || npm install --silent --no-audit --no-fund
  node esbuild.config.mjs
  cd "$PROJECT_ROOT"
  echo -e "${GREEN}  aw CLI built${NC}"
else
  echo -e "${RED}  CLI package.json missing${NC}"
  exit 1
fi

# Phase 6: Validate
echo -e "${BLUE}[6/7] Validating...${NC}"
errors=0
for plugin_dir in "$PLUGINS_DIR"/*; do
  [[ ! -d "$plugin_dir" ]] && continue
  plugin_name=$(basename "$plugin_dir")
  if [[ ! -f "$plugin_dir/.claude-plugin/plugin.json" ]]; then
    echo -e "${RED}  $plugin_name: Missing plugin.json${NC}"
    errors=$((errors + 1))
  elif ! jq empty "$plugin_dir/.claude-plugin/plugin.json" 2>/dev/null; then
    echo -e "${RED}  $plugin_name: Invalid JSON in plugin.json${NC}"
    errors=$((errors + 1))
  fi
  if [[ ! -f "$plugin_dir/hooks/dist/lifecycle.mjs" ]]; then
    echo -e "${RED}  $plugin_name: Missing hooks/dist/lifecycle.mjs${NC}"
    errors=$((errors + 1))
  fi
  if [[ ! -f "$plugin_dir/hooks/hooks.json" ]]; then
    echo -e "${RED}  $plugin_name: Missing hooks/hooks.json${NC}"
    errors=$((errors + 1))
  fi
  if [[ ! -f "$plugin_dir/guide/index.html" ]]; then
    echo -e "${RED}  $plugin_name: Missing guide/index.html${NC}"
    errors=$((errors + 1))
  fi
  if [[ ! -x "$plugin_dir/bin/aw" ]]; then
    echo -e "${RED}  $plugin_name: Missing bin/aw${NC}"
    errors=$((errors + 1))
  fi
done
if [[ $errors -gt 0 ]]; then
  echo -e "${RED}  Validation failed with $errors error(s)${NC}"
  exit 1
fi
echo -e "${GREEN}  Validation passed${NC}"

# Phase 7: Summary
echo -e "${BLUE}[7/7] Summary${NC}"
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  BUILD COMPLETE${NC}"
echo -e "${CYAN}============================================${NC}"
echo -e "  Output: ${GREEN}$PLUGINS_DIR${NC}"
for plugin_dir in "$PLUGINS_DIR"/*; do
  [[ ! -d "$plugin_dir" ]] && continue
  plugin_name=$(basename "$plugin_dir")
  echo -e "  Plugin: ${GREEN}$plugin_name${NC}"
  echo -e "    Skills:   $(find "$plugin_dir/skills" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')"
  echo -e "    Agents:   $(find "$plugin_dir/agents" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
done
