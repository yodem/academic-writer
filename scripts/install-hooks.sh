#!/bin/bash
# Install git hooks for the Academic Writer plugin.
# Run once after cloning: bash scripts/install-hooks.sh

set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"

echo "Installing Academic Writer git hooks..."

# Pre-push: run validation tests before every push
cat > "$HOOKS_DIR/pre-push" << 'HOOK'
#!/bin/bash
# Academic Writer — pre-push validation hook
# Runs the full test suite before allowing a push.

set -e

echo "Academic Writer: Running pre-push validation..."
echo "================================================"

cd "$(git rev-parse --show-toplevel)"

if python3 -m unittest discover tests/ -v 2>&1; then
    echo ""
    echo "================================================"
    echo "All tests passed. Push proceeding."
    echo "================================================"
    exit 0
else
    echo ""
    echo "================================================"
    echo "PUSH BLOCKED: Tests failed. Fix the issues above before pushing."
    echo "================================================"
    exit 1
fi
HOOK

chmod +x "$HOOKS_DIR/pre-push"
echo "  ✓ pre-push hook installed"

echo ""
echo "Done. Git hooks are active."
echo "Tests will run automatically before each push."
