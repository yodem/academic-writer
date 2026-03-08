#!/usr/bin/env bash
# Ingest a document into Agentic-Search-Vectorless
# Usage: vectorless-ingest.sh --name "Document Title" --content "Full text content"
#    or: vectorless-ingest.sh --name "Document Title" --file /path/to/content.txt
# Output: JSON response with documentId

set -euo pipefail

VECTORLESS_URL="${VECTORLESS_URL:-http://localhost:8000}"
NAME=""
CONTENT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) NAME="$2"; shift 2 ;;
    --content) CONTENT="$2"; shift 2 ;;
    --file) CONTENT=$(cat "$2"); shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$NAME" ]] && echo "Error: --name required" >&2 && exit 1
[[ -z "$CONTENT" ]] && echo "Error: --content or --file required" >&2 && exit 1

# Use python3 to safely build JSON (handles Hebrew/Unicode, escaping)
python3 -c "
import json, sys
data = {'name': sys.argv[1], 'content': sys.argv[2], 'docType': 'text'}
print(json.dumps(data, ensure_ascii=False))
" "$NAME" "$CONTENT" | curl -s -X POST "$VECTORLESS_URL/documents" \
  -H "Content-Type: application/json" \
  -d @-
