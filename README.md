# IP-SAKTI Sahayak (आईपी-शक्ति सहायक)

**Evidence-Grounded Intellectual Property and Regulatory Intelligence Copilot for Ayurveda**

> Retrieve First. Reason Second. Cite Third. Verify Always.

IP-SAKTI Sahayak helps Ayurveda researchers, startups, MSMEs, patent and regulatory professionals navigate IP, traditional knowledge (TK), scientific evidence and regulation across **India, the USA and Australia**. It is a **decision-support and evidence-orchestration platform**. It is *not* a patent agent, lawyer, regulator, medical advisor, TKDL mirror, filing system or approval predictor, and it never claims to be.

---

## Features

| Area | What it does |
|---|---|
| Auth & workspaces | Register/login (bcrypt + JWT in an httpOnly cookie), workspace RBAC (OWNER/ADMIN/RESEARCHER/REVIEWER/VIEWER), workspace isolation, CSRF header check, session expiry |
| Innovation Profiler | 7-step wizard → structured profile, technical features, terminology normalisation, missing information and ambiguities (never invented), user editing/confirmation |
| Terminology engine | Sanskrit / Hindi / English / botanical / chemical mapping; ambiguous common names (e.g. *Brahmi*) are flagged, not silently mapped |
| AI Research Assistant | Conversations, 6 modes, language/jurisdiction/source filters, structured answers (answer → key points → evidence → status → limitations → next step), copy/regenerate/feedback/flag, add-to-innovation |
| Hybrid RAG | pgvector dense + Postgres full-text (BM25-style) + metadata + graph expansion → dedupe → deterministic rerank (relevance, lexical, jurisdiction, authority tier, freshness, document type, feature match); full search trace stored per answer |
| Citation verification | Claim extraction → citation binding → source/passage existence, authority, jurisdiction, freshness, section/year anchors, semantic support (+ LLM entailment when configured) → SUPPORTED / PARTIALLY / UNSUPPORTED / CONFLICTING / INSUFFICIENT |
| Safety | Abstention engine, jurisdiction clarification, unsupported-jurisdiction refusal, medical and legal-certainty boundaries, restricted-TKDL refusal, prompt-injection detection in queries and documents |
| Conflicts & freshness | Conflicting sources shown side by side; superseded documents excluded unless requested; Current / Recently checked / Potentially stale / Superseded / Unknown |
| Scientific evidence | Study cards that keep **ingredient** evidence separate from **final-formulation** evidence |
| Patents / prior art | Search concepts, feature-to-document matrix with filters, patent-family grouping, review status; overlap is never presented as a patentability verdict |
| Traditional knowledge | Public/authorised context only, access limits, attribution, possible-overlap notes, escalation |
| Classification & regulatory | Guided questionnaire → provisional category per jurisdiction with assumptions, facts that could change it, missing questions; Regulatory Passport; India/USA/Australia comparison table |
| Evidence intelligence | Automatic evidence gaps (LOW → CRITICAL), 8-category risk map, interactive evidence graph (React Flow) with provenance on every edge |
| Human review | IP / regulatory / domain / general escalations with full evidence packets and status workflow |
| Reports | Evidence report (all sections from the spec) with Markdown export and print-to-PDF |
| Corpus & admin | Source registry, documents, validated upload/ingestion pipeline, ingestion jobs, users, workspaces, system health, RAG evaluation dashboard |
| Governance (gap analysis) | Jurisdiction coverage matrix (Built/Partial/Planned, computed), provision map, heuristic confidence with visible signals, explicit TKDL status, structured feedback queue, corpus update queue with curators, retention purge, data-handling page, cost/latency metrics — see `docs/GAP_CLOSURE.md` |
| Audit & observability | Audit trail for all key actions (IP stored only as salted hash), structured JSON request logs with request_id/user/workspace/latency |
| Multilingual | English and Hindi UI; Hindi questions are answered via terminology expansion over English sources, preserving names, section numbers and titles |

## Architecture

```
Browser ──► Next.js 15 (App Router, TanStack Query, Tailwind, React Flow)
              │  /api/* rewritten to FastAPI (single origin; cookie auth)
              ▼
         FastAPI (Pydantic, SQLAlchemy 2, Alembic)
           ├─ api/endpoints   auth, workspaces, innovations, chat, search, review, corpus, admin, evaluations, health
           ├─ services        research pipeline, retrieval, verification, terminology, profile, patents,
           │                  evidence, regulatory, analysis (gaps/risk/graph), packets, ingestion, evaluation, llm, audit
           └─ seed            curated corpus + demo users/workspace/innovation
              ▼
         PostgreSQL 16 + pgvector (HNSW cosine index, GIN tsvector index)
```

- **LLM:** a provider abstraction with `openai`, `deepseek` (OpenAI-compatible) and `mock` backends. With `mock`, answers are **extractive**: they quote retrieved passages and are still verified. Nothing is synthesised without a source.
- **Embeddings:** `hashing` (default: offline character/word n-gram hashing, 1024-d), `openai` (text-embedding-3-small at 1024-d) or `bge_m3` (local). DeepSeek has no embeddings API, so pair it with `hashing` or `openai`.

## Folder structure

```
backend/
  app/{main.py, db.py, schemas.py, core/, api/endpoints/, models/orm.py, services/, seed/}
  alembic/ (migrations)        requirements.txt
rag/embeddings/provider.py     embedding providers (hashing, openai, bge-m3, mock)
rag/, ingestion/               earlier local-store retriever, PDF parser and section-aware chunker (reused by ingestion)
frontend/
  app/ (landing, login, register, app/**)   components/   lib/ (api, i18n, providers, hooks, types)
tests/                          pytest suite incl. the end-to-end integration flow
docker/                         backend & frontend Dockerfiles      docker-compose.yml
```

## Running locally

**Prerequisites:** Python 3.11+ (3.13 tested), Node 20+ (24 tested), Docker (for Postgres).

```bash
cp .env.example .env              # then set JWT_SECRET and SESSION_SECRET to long random strings
docker compose up -d postgres     # Postgres 16 + pgvector on localhost:5433

python3.13 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt

cd backend
../.venv/bin/alembic upgrade head                        # create schema
PYTHONPATH=.:.. ../.venv/bin/python -m app.seed.run      # seed corpus, demo users and demo innovation (--reset to reseed)
PYTHONPATH=.:.. ../.venv/bin/uvicorn app.main:app --port 8000
# API docs: http://localhost:8000/docs

cd ../frontend && npm install && npm run dev             # http://localhost:3000
```

**Everything in Docker:** `docker compose up --build`. The backend container migrates and seeds itself on first boot.

### Enabling a real LLM (recommended)

**Free & private (default in this repo): local Ollama.** No key, and nothing leaves the machine.

```bash
ollama pull qwen2.5:7b      # ~4.7 GB; llama3.2 (2 GB) also works but gives weaker Hindi answers
```
```env
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:7b
```

**Hosted APIs.** All are OpenAI-compatible and need only `LLM_PROVIDER` and `LLM_API_KEY`:

| Provider | Base URL (automatic) | Notes |
|---|---|---|
| `gemini` | Google AI Studio OpenAI endpoint | Free tier; prompts may be used by Google on free tier |
| `groq` | api.groq.com | Free tier with rate limits; hosted open models |
| `grok` | api.x.ai | xAI, paid |
| `openai` / `deepseek` | — | paid |

Model names change over time. Set `LLM_MODEL` to one the provider currently lists. Keep `.env` comments on their own lines, never after a value.

Restart the backend and check `GET /health/llm` (or Admin → System Health). With a key: answers are synthesised (and verified), Hindi answers are generated in Hindi, Hindi queries are translated for retrieval, each claim gets an LLM entailment check, profile extraction adds AI-suggested features (marked *needs confirmation*), and cost per query is measured. If the provider fails at runtime, answers fall back to extractive mode and say so.

## Demo

Logins (password `Demo@12345`): `researcher@ipsakti.demo` (Researcher), `reviewer@ipsakti.demo` (Reviewer), `admin@ipsakti.demo` (Owner + system admin). **Explore Demo** on the landing page pre-fills the researcher login.

Hackathon flow: Login → Dashboard → *AyuCalm-X (DEMO)* → Profile (note the Brahmi ambiguity and the disease-claim flag) → *Ask about this innovation* (citations, verification, search trace, conflicting sources) → Scientific (ingredient vs formulation) → Patents (feature matrix, families) → Traditional Knowledge → Classification → Regulatory Passport (India / USA / Australia and comparison) → Gaps & Risk → Evidence Graph (click nodes and edges) → Escalation & Report → export → Audit Trail. Admins additionally see System Health, Source Registry, Ingestion and **RAG Evaluation** (run it live).

Useful assistant prompts: the six example cards on the empty chat screen cover a factual question, a regulatory question, a cross-jurisdiction question, a Hindi question, prior art and a restricted-TKDL refusal.

## Data & source policy

| Label | Meaning |
|---|---|
| `SEED_SUMMARY` | Short excerpts or close summaries of **real** public instruments and publications. Verify them against the official Gazette, regulator or journal text before relying on them. |
| `DEMO_FICTIONAL` | **Fictional** records: every patent (`DEMO-…` numbers), the two conflicting "DEMO (fictional)" guidance notes, and the AyuCalm-X innovation. |
| `PENDING_REVIEW` | User uploads (Tier 5), which are workspace-private and unverified. |

Source tiers: 1 official law/regulator · 2 international official · 3 peer-reviewed · 4 secondary/demo · 5 user-provided/unverified. TKDL: the system has **no** TKDL access and never scrapes or reproduces restricted records.

## Security

- bcrypt password hashing and password rules; JWT in an httpOnly SameSite=Lax cookie (or a Bearer token for API clients).
- `X-Requested-With` header required on cookie-authenticated writes (CSRF defence).
- Workspace isolation on every innovation, conversation, document, report and escalation query; RBAC per workspace role; admin-only endpoints.
- Pydantic validation on all inputs; SQLAlchemy/bound parameters only (no string SQL with user input); React escaping and no raw HTML rendering.
- Upload checks: extension allowlist, magic-byte signature, size limit, UTF-8 check, PDFs with JavaScript/Launch actions rejected, text sanitised, duplicate hash detection.
- Retrieved text is treated as **data**. Instruction-like text is flagged at ingestion, down-ranked, labelled in the UI, excluded from key points, and the LLM prompt forbids following it.
- Rate limits on chat, search, ingest and reports; security headers; restricted CORS; the error envelope never leaks stack traces.
- Structured logs never include request bodies or confidential innovation text.

## Testing

```bash
docker compose up -d postgres
.venv/bin/python -m pytest -q          # uses a separate ipsakti_test database, migrated and seeded automatically
```

54 tests cover (incl. LLM mode via a fake provider, OCR, coverage, provisions, feedback, lifecycle):
- auth, RBAC, CSRF and workspace isolation;
- upload validation and injection flagging;
- retrieval relevance, irrelevant-query rejection and jurisdiction filtering;
- supersession, supported/contradicted/unsupported citations and conflict detection;
- clarification, TKDL, unsupported-jurisdiction and prompt-injection handling;
- medical and legal boundaries, and Hindi;
- the **full end-to-end flow** (user → workspace → innovation → profile → research → verify → patents → regulatory comparison → gaps → escalation → report → audit);
- the evaluation suite run.

## Known limitations

- The corpus is a curated seed (40 documents), not a live feed. Statute summaries need verification, and patents are fictional. Use Admin → Ingestion to add official documents.
- The default `hashing` embeddings capture shared vocabulary, not synonyms (terminology expansion covers much of this). Use `EMBEDDING_PROVIDER=openai` or `bge_m3` for semantic embeddings. Changing the embedding provider requires reseeding (`--reset`) so stored vectors match.
- Without an LLM key, answers are extractive quotes rather than synthesis.
- OCR is not enabled: scanned PDFs are rejected with a clear message.
- Rate limiting is in-process; use Redis for multi-instance deployments.
- Background jobs run inline (documents are small); long ingestion would need a worker.
- Legacy artifacts from the earlier prototype (`backend/db/schema.sql`, `rag/store/*`, `evaluation/`, `scripts/`) are kept for reference; Alembic migrations and `app/models/orm.py` are the source of truth.
