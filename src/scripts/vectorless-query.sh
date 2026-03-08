#!/usr/bin/env bash
# Query Agentic-Search-Vectorless
# Usage: vectorless-query.sh --query "search text" [--mode mix|bypass|local|global] [--doc-id ID] [--top-k N]
# Output: JSON response with answer, context, metadata

set -euo pipefail

VECTORLESS_URL="${VECTORLESS_URL:-http://localhost:8000}"
QUERY=""
MODE="mix"
DOC_ID=""
TOP_K=20
RERANK_TOP_K=8

while [[ $# -gt 0 ]]; do
  case "$1" in
    --query) QUERY="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --doc-id) DOC_ID="$2"; shift 2 ;;
    --top-k) TOP_K="$2"; shift 2 ;;
    --rerank-top-k) RERANK_TOP_K="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$QUERY" ]] && echo "Error: --query required" >&2 && exit 1

# Build JSON safely with python3 (handles Hebrew/Unicode)
python3 -c "
import json, sys
data = {
    'query': sys.argv[1],
    'mode': sys.argv[2],
    'top_k': int(sys.argv[3]),
    'rerank_top_k': int(sys.argv[4]),
    'enable_rerank': True,
    'include_context': True
}
doc_id = sys.argv[5]
if doc_id:
    data['documentId'] = doc_id
print(json.dumps(data, ensure_ascii=False))
" "$QUERY" "$MODE" "$TOP_K" "$RERANK_TOP_K" "$DOC_ID" | curl -s -X POST "$VECTORLESS_URL/query" \
  -H "Content-Type: application/json" \
  -d @-
