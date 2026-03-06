# HybridRAG API — External Service Integration Prompt

You are communicating with a local HybridRAG REST API server. Use this reference to interact with it correctly.

---

## Starting the Server

```bash
# Start MongoDB Atlas local (if not running)
atlas deployments start hybridrag

# Start the API server (default: http://localhost:8000)
uvicorn src.hybridrag.api.main:app --host 0.0.0.0 --port 8000
```

The server auto-docs are at: http://localhost:8000/docs

---

## Base URL

```
http://localhost:8000
```

---

## Endpoints

### Health check
```
GET /health
```
Response: `{ "status": "healthy", "components": {...}, "version": "..." }`

---

### Ingest documents
```
POST /v1/ingest
Content-Type: application/json

{
  "documents": ["Full text of document 1...", "Full text of document 2..."],
  "ids": ["doc-1", "doc-2"]   // optional — auto-generated if omitted
}
```
Response:
```json
{ "status": "success", "documents_processed": 2, "message": "..." }
```

---

### Query
```
POST /v1/query
Content-Type: application/json

{
  "query": "Your question here",
  "mode": "mix",           // local | global | hybrid | naive | mix | bypass
  "top_k": 60,             // candidates to retrieve (1–200)
  "rerank_top_k": 10,      // results after reranking (1–50)
  "enable_rerank": true,
  "include_context": false // set true to get source chunks alongside the answer
}
```
Response:
```json
{
  "answer": "The synthesized answer...",
  "context": "Source passages... (only if include_context=true)",
  "metadata": { "mode": "mix", "top_k": 60, "rerank_top_k": 10 }
}
```

**Mode guide:**
- `mix` — best overall, use as default
- `bypass` — raw retrieval, best for exact quotes and page numbers
- `local` — deep dive on a specific entity or concept
- `global` — thematic overview across all documents

---

### Delete a document
```
DELETE /v1/documents/{doc_id}
```
Response: `{ "status": "deleted", "doc_id": "..." }`

---

### System status
```
GET /v1/status
```

---

## Example: Precise quote retrieval

```json
POST /v1/query
{
  "query": "What does Kant say about the categorical imperative? Give the exact quote and page number.",
  "mode": "bypass",
  "top_k": 20,
  "rerank_top_k": 5,
  "include_context": true
}
```

---

## Error format
```json
{ "error": "string", "detail": "string", "code": "string" }
```
HTTP status codes: `400` bad request · `500` server error · `503` not initialized
