#!/usr/bin/env bash
# List documents ingested in Agentic-Search-Vectorless
# Usage: vectorless-list.sh
# Output: One line per document: DOCUMENT_ID  NAME

set -euo pipefail

VECTORLESS_URL="${VECTORLESS_URL:-http://localhost:8000}"

curl -s "$VECTORLESS_URL/documents" | python3 -c "
import sys, json
docs = json.load(sys.stdin).get('documents', [])
for d in docs:
    print(d.get('document_id', '?'), d.get('name', '?'))
"
