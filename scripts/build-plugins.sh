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
command -v jq &>/dev/null || { echo -e "${RED}Error: jq required. Install with: brew install jq${NC}"; exit 1; }
echo -e "${GREEN}  Environment OK${NC}"

# Phase 2: Build hooks
echo -e "${BLUE}[2/6] Building TypeScript hooks...${NC}"
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
  if [[ -d "$SRC_DIR/skills" ]]; then
    cp -R "$SRC_DIR/skills" "$PLUGIN_DIR/"
  fi
  skill_count=$(find "$PLUGIN_DIR/skills" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')

  # Copy agents
  if [[ -d "$SRC_DIR/agents" ]]; then
    cp -R "$SRC_DIR/agents" "$PLUGIN_DIR/"
  fi
  agent_count=$(find "$PLUGIN_DIR/agents" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')

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

  # Copy shared resources
  if [[ -f "$SRC_DIR/words.md" ]]; then
    cp "$SRC_DIR/words.md" "$PLUGIN_DIR/"
  fi

  # Copy workflow definitions
  if [[ -d "$SRC_DIR/workflows" ]]; then
    cp -R "$SRC_DIR/workflows" "$PLUGIN_DIR/"
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
      keywords: ["academic-writing","humanities","citations","claude-code","plugin"]
    }' > "$PLUGIN_DIR/.claude-plugin/plugin.json"

  # Generate commands from user-invocable skills
  if [[ -d "$PLUGIN_DIR/skills" ]]; then
    for skill_md in "$PLUGIN_DIR/skills"/*/SKILL.md; do
      [[ ! -f "$skill_md" ]] && continue
      if grep -q "^user-invocable: *true" "$skill_md"; then
        skill_name=$(basename "$(dirname "$skill_md")")
        mkdir -p "$PLUGIN_DIR/commands"
        # Extract description and allowed-tools from frontmatter using awk
        description=$(awk '/^---$/{n++; next} n==1 && /^description:/{sub(/^description: *"?/,""); sub(/"$/,""); print; exit}' "$skill_md")
        allowed_tools=$(awk '/^---$/{n++; next} n==1 && /^allowed-tools:|^allowedTools:/{sub(/^(allowed-tools|allowedTools): */,""); print; exit}' "$skill_md")
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

  echo -e "${GREEN}  Built $PLUGIN_NAME v$PLUGIN_VERSION: $skill_count skills, $agent_count agents, $command_count commands${NC}"
done

# Phase 5: Validate
echo -e "${BLUE}[5/6] Validating...${NC}"
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
done
if [[ $errors -gt 0 ]]; then
  echo -e "${RED}  Validation failed with $errors error(s)${NC}"
  exit 1
fi
echo -e "${GREEN}  Validation passed${NC}"

# Phase 6: Summary
echo -e "${BLUE}[6/6] Summary${NC}"
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  BUILD COMPLETE${NC}"
echo -e "${CYAN}============================================${NC}"
echo -e "  Output: ${GREEN}$PLUGINS_DIR${NC}"
for plugin_dir in "$PLUGINS_DIR"/*; do
  [[ ! -d "$plugin_dir" ]] && continue
  plugin_name=$(basename "$plugin_dir")
  echo -e "  Plugin: ${GREEN}$plugin_name${NC}"
  echo -e "    Skills:   $(find "$plugin_dir/skills" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')"
  echo -e "    Agents:   $(find "$plugin_dir/agents" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
  echo -e "    Commands: $(find "$plugin_dir/commands" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
done
