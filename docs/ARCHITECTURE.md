# IP-SAKTI Sahayak — Architecture & Runtime

## Boundary

IP-SAKTI Sahayak is a **decision-support and evidence-orchestration** platform for Ayurveda IP, traditional knowledge, scientific evidence and regulation in India, the USA and Australia.

It is **not** any of the following:
- a patent agent, lawyer, regulator or medical advisor;
- a TKDL mirror;
- a filing system;
- an approval predictor.

It never states that something is patentable, that there is freedom to operate, or that a product will be approved.

## Runtime boundary (where each piece actually runs)

| Component | Runs in | Notes |
|---|---|---|
| UI | Next.js 15 (`next start`, Node) | Presentation only. `/api/*` is rewritten to FastAPI so the browser talks to one origin. |
| API & orchestration | FastAPI + Uvicorn (Python 3.13) | Auth, RBAC, research pipeline, verification, classification, reports. |
| Dense retrieval | **PostgreSQL 16 + pgvector** (HNSW, cosine) | Query vectors are computed in the API process. |
| Lexical retrieval | **PostgreSQL full-text** (generated `tsvector`, GIN) | BM25-style `ts_rank_cd`. |
| Embeddings | `hashing` (default): in-process CPU, no network, ~1 ms | `openai` (managed API) and `bge_m3` (local CPU/GPU, ~2 GB model) are optional. |
| Reranking | Deterministic scoring in-process | No cross-encoder. This keeps latency low and the ranking explainable. |
| Generation | `openai`/`deepseek` API or none (extractive) | Model-agnostic `LLMProvider`. Any OpenAI-compatible server (vLLM, Ollama) works via `LLM_BASE_URL`. |
| Ingestion / OCR | FastAPI background task (off the request path) | Pipeline: PyMuPDF → Tesseract OCR fallback → section-aware chunker → embed → index. The raw file is deleted afterwards. |
| Observability | JSON logs per request | Fields: request_id, user, workspace, endpoint, status, latency. Every answer also stores its full retrieval trace and LLM token usage. |

Not on Vercel serverless: the API needs a long-lived Python process and a Postgres connection. Suggested institutional hosting:
- 1 small VM (2 vCPU / 4 GB) running API + UI;
- managed Postgres with pgvector;
- a GPU worker only if `bge_m3` embeddings are chosen.

## Measured performance (seed corpus, hashing embeddings, extractive mode)

From **Admin → RAG Evaluation**, 20 questions:
- **Latency:** p50 10 ms, p95 20 ms for the pipeline itself.
- **With an LLM:** add the provider's latency (typically 1–4 s) and one entailment call per key point.
- **Corpus:** 39 global documents, 81 chunks, 13 global sources.
- **Bottleneck:** the LLM, when configured. Retrieval stays under 30 ms at this size, and pgvector HNSW scales to millions of chunks.

## Research pipeline

```
query → language detection → intent → jurisdiction (hard filter; EU and other unsupported jurisdictions are refused)
      → [Hindi + LLM: meaning-preserving translation to English]
      → terminology normalisation (Sanskrit/Hindi/English/botanical/chemical; ambiguity flagged)
      → query expansion → source selection
      → hybrid retrieval: dense (pgvector) + BM25 (tsvector) + metadata (keywords) + graph (curated document relations)
      → merge → dedupe → deterministic rerank (relevance, lexical, jurisdiction, tier, freshness, doc type, feature match;
        injection-flagged text down-weighted)
      → context assembly (top-k passages, truncated, delimited as DATA)
      → generation (LLM JSON with answer-language text + English text_en) or extractive quotes
      → claim extraction → citation binding (fabricated citation numbers removed and reported)
      → verification per claim: source exists → passage exists → authority → jurisdiction → freshness
        → anchors (section/rule/year present in passage) → lexical coverage + embedding similarity
        → polarity check on best-matching sentence → optional LLM entailment
        → SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED / CONFLICTING / INSUFFICIENT
      → conflict detection (same topic, different positions) → freshness check
      → safety/abstention (TKDL, medical, legal certainty, injection, insufficient evidence)
      → heuristic confidence with visible signals → response + stored trace
```

## Confidence

Confidence is a **heuristic**, not a calibrated probability. It is a weighted mix of six signals:

| Signal | Weight |
|---|---|
| Claim verification score | 0.30 |
| Share of claims fully supported | 0.20 |
| Source authority tier | 0.20 |
| Jurisdiction match | 0.10 |
| Evidence coverage | 0.10 |
| Freshness | 0.10 |

It is then reduced by penalties for ambiguous terms, source conflicts and demo sources. The UI shows every signal under "Why this confidence?".

## Data model (Alembic migrations in `backend/alembic/versions`)

**Tenancy:**
- users, organizations, workspaces, workspace_members (RBAC).

**Innovations:**
- innovations, innovation_profiles, innovation_features;
- evidence, patent_feature_matches, evidence_gaps;
- escalations, reports.

**Corpus:**
- sources (tier, jurisdiction, access level, update frequency, curator);
- documents (version, effective date, supersession, content hash, extraction method, OCR confidence, review status);
- document_chunks (section, chunk type, embedding, tsvector, injection flag);
- patents, scientific_studies, regulatory_pathways, terms (terminology).

**Research, quality and audit:**
- conversations, messages (structured payload + trace), retrieval_results;
- claims and claim_evidence (per-claim verification records);
- feedback (issue reports with snapshots);
- evaluation_questions, evaluation_runs;
- ingestion_jobs, audit_logs.
