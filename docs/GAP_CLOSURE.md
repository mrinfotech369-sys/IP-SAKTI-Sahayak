# IP-SAKTI Sahayak — Gap Closure against the MVP Gap Analysis

This document answers the MVP Gap Analysis (PS 26045, Team PhantomX) item by item.

**Status key:**
- **Done:** implemented, tested and visible in the UI.
- **Partial:** implemented with a stated limit.
- **Open:** not done.

Figures come from the live system: *Admin → RAG Evaluation*, *Coverage Matrix* and *System Health*. Re-run them before quoting, because the numbers change when the corpus or model changes.

## 1. Priority gap matrix

| Pri | Gap | Status | What exists now (where to see it) |
|---|---|---|---|
| P0 | Multilingual | **Done** (Hindi) | See **Multilingual detail** below. |
| P0 | Evaluation | **Done** | 20-question labelled set; baselines (BM25-only, no-safety-gate, LLM-only when a key is set); 13 labelled classification decisions; p50/p95 latency (Admin → RAG Evaluation). |
| P0 | Citation verification | **Done** | See **Citation verification detail** below. |
| P0 | TKDL consistency | **Done** | "TKDL access: restricted — not queried" is shown in chat, the TK tab, the summary and reports. Public TK sources are shown separately as "searched". Full-TKDL requests are refused. No negative prior-art result is ever implied. |
| P0 | International coverage | **Done** | Coverage Matrix computed from the corpus. India, USA and Australia regulatory are Built. EU is Planned, and EU questions are refused. |
| P1 | Privacy & security | **Partial** | See **Privacy & security detail** below. |
| P1 | Confidence | **Done** | Labelled "heuristic, not calibrated"; "Why this confidence?" shows 6 weighted signals plus penalties. |
| P1 | Legal-domain depth | **Done** | Provision map: 21 provisions (Patents Act s.3(p)/(d)/(e), 10(4), 25(1); BD Act s.3/6/7; D&C Act 3(a)/3(h); Rule 158B; Schedule T; DMR Act; 21 CFR 101.93, Part 111; 21 U.S.C. 321(ff), 321(g), 350b; TGA s.26A, permissible indications, AUST R; WIPO GR/ATK Art. 3; Nagoya Arts. 5/7). Each is flagged against the innovation with a reason and a link to its source passage. The label says "not a determination". |
| P1 | Corpus lifecycle | **Done** | See **Corpus lifecycle detail** below. |
| P1 | Deployment realism | **Done** | `docs/ARCHITECTURE.md` gives the runtime boundary table and measured latency. Ingestion and OCR run as background jobs. The model layer is provider-agnostic. |
| P1 | Domain vocabulary | **Done** | Terminology engine covering Sanskrit, Hindi, English, botanical, chemical and aliases, with ambiguity (Brahmi → *Bacopa monnieri* / *Centella asiatica*). Synonym retrieval tests: E17 Haridra/Maricha, E18 *Withania somnifera*, E19 Hindi. |
| P1 | Prompt injection | **Done** | See **Prompt-injection detail** below. |
| P2 | Feedback & audit | **Done** | "Report issue" form: category, reason, key point, answer + source-version snapshot, review status. Feedback queue. Audit trail. Every answer stores its full retrieval trace. |
| P2 | Upload | **Done** | Privacy/retention notice with a required acknowledgement. Validation. Background ingestion with Tesseract OCR fallback and OCR confidence; OCR below 70 forces human validation. The raw file is deleted after processing. |
| P2 | Export | **Done** | See **Export detail** below. |
| P2 | Cost/scalability | **Partial** | p50/p95, LLM calls per query, cost per query and a 10k-user projection come from recorded token usage (System Health). The cost is **$0 until an LLM key is configured**. Price assumptions are configurable. |

### Multilingual detail

- **UI:** full English/हिन्दी chrome, including the language selector on the landing page and in the header.
- **Query handling:**
  - Hindi is detected automatically.
  - Hindi terms map to English through the terminology engine, with no LLM needed.
  - With an LLM, the query gets a meaning-preserving translation to English for retrieval.
- **Answers:**
  - Written in Hindi.
  - Each key point is verified through its English rendering (`text_en`).
- **Languages shown:** answer language and source language are displayed separately.
- **Tests:** `test_hindi_query`, `test_hindi_query_translated_answered_in_hindi_and_verified_in_english`.

### Citation verification detail

- **Deterministic checks per claim:**
  - source exists and passage exists;
  - authority tier;
  - jurisdiction;
  - freshness and supersession;
  - section/rule/year anchors present in the passage;
  - lexical coverage and embedding similarity;
  - negation polarity on the best-matching sentence;
  - optional LLM entailment.
- **Citation hygiene:** fabricated citation numbers are removed and reported.
- **UI:** a claim → [n] → exact passage drawer.

### Privacy & security detail

- **Done:**
  - sensitive-input warning and required acknowledgement;
  - upload notice;
  - per-workspace isolation and RBAC;
  - bcrypt passwords and salted-hash IPs;
  - LLM provider data-handling statement (Data & Privacy page);
  - enforceable retention purge.
- **Open:** encryption at rest relies on the host or managed-database encryption, not application-level encryption.

### Corpus lifecycle detail

- **Source registry fields:** tier, jurisdiction, access, URL, update frequency, curator.
- **Document fields:** version, effective date, ingestion date, supersedes/superseded-by, review status, content hash.
- **Update Queue:** Overdue / Review due / Superseded, with actions Mark checked / Approve / Mark superseded, all audited.
- **Behaviour:** superseded documents are excluded from answers.

### Prompt-injection detail

- Retrieved and uploaded text is delimited as data.
- Instruction-like text is flagged at ingestion, down-ranked in retrieval, labelled in the UI, and excluded from key points.
- The system prompt forbids following instructions found in passages.
- Tested with a seeded malicious upload.

### Export detail

- **Report order:**
  1. profile → classification → provision map;
  2. TK → science → patents → feature matrix;
  3. passport → comparison → gaps → risk;
  4. citation verification → conflicts → next steps → open questions → limitations;
  5. sources → **source versions used** → audit.
- **Formats:** Markdown download or print-to-PDF.

## 2. The 18 questions

1. **Multilingual — which languages work?**
   - English and Hindi, end to end.
   - Without an LLM: Hindi UI, Hindi query handling via the terminology engine, and extractive English passages with Hindi framing.
   - With an LLM: fully Hindi answers, each verified through its English rendering.
   - No other language is claimed.
2. **How do you verify a citation supports the claim?**
   - Ten deterministic checks, listed in the architecture doc. The key ones:
     - source and passage exist;
     - jurisdiction match;
     - freshness and supersession;
     - section/rule anchors present;
     - lexical coverage and semantic similarity;
     - negation polarity on the best-matching sentence;
     - LLM entailment when available.
   - Output: SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED / CONFLICTING / INSUFFICIENT, shown per key point.
   - Tests cover supported, contradicted and unrelated claims.
3. **Performance on a labelled set?**
   - 20-question set, latest run:
     - recall@6 **0.978** vs **0.822** for a keyword-only baseline;
     - citation entailment **0.95**;
     - unsupported-claim rate **0**;
     - abstention accuracy **1.0** vs **0.85** for an always-answer baseline;
     - jurisdiction accuracy **1.0**;
     - cross-jurisdiction contamination **0** vs **0.22** for the baseline;
     - classification agreement **13/13** on author-labelled cases (expert review pending);
     - 19/20 questions pass all checks.
   - **LLM mode** (local `qwen2.5:7b` via Ollama, same 20 questions):
     - abstention accuracy **1.0** vs **0.8** for the same model answering without retrieval;
     - citation correctness **1.0**; the no-retrieval model gives 0% verifiable citations;
     - citation entailment **0.80** (paraphrases verify less often than quotes; such points are shown as *partially supported*, never as fact);
     - unsupported-claim rate **3.2%**, flagged in the UI;
     - latency p50 33 s / p95 55 s on a 16 GB M4 laptop (measured while a frontend build was running).
   - Caveat: the questions were written by the team against a small curated corpus. Treat this as a regression suite, not a benchmark claim.
4. **Corpus size — what is ingested?**
   - 39 global documents, 81 passages, 13 global sources (plus a workspace-upload source and a demo malicious upload used for injection tests): 26 statute/regulation/treaty/TK-context documents, 6 peer-reviewed studies and 7 patents.
   - 9 of the 39 are demo/fictional, clearly labelled: all 7 patents and 2 conflict-demo notes.
   - The live list is on the Coverage Matrix and Documents pages.
5. **Which international jurisdictions are built?**
   - USA (FDA: DSHEA, 21 CFR 101.93, NDI, Part 111, drug definition and botanical guidance) and Australia (TGA: s.26A/26AE, permissible indications, evidence guidelines, registered CMs).
   - EU is **Planned**: not ingested, and questions are refused.
6. **TKDL access?**
   - **No.** The UI shows "TKDL access: restricted — not queried" wherever TK is involved, and separates it from the public/authorised sources that *were* searched.
   - Requests for TKDL records are refused.
7. **Sanskrit, vernacular and Latin synonyms?**
   - A terminology table (Sanskrit, Hindi, English, botanical, chemical, aliases) expands queries and normalises profiles.
   - Ambiguous names are flagged, not guessed.
   - Retrieval tests: E17 (Haridra + Maricha → piperine study), E18 (*Withania somnifera*), E19 (Hindi अश्वगंधा).
8. **Amendments and outdated regulations?**
   - Every document carries version, effective date and last-checked date.
   - Supersession links exclude old versions: the FSSAI 2016 regulations are superseded by the 2022 regulations, and the old version is only returned on request, labelled "Superseded".
   - The Update Queue flags documents past their source's update frequency; the named curator re-verifies them.
9. **Unpublished formulation submitted?**
   - A confidential-mode acknowledgement is required.
   - A warning appears on every screen of that innovation.
   - Data stays in its workspace.
   - Request logs never contain body text.
   - Only retrieved passages plus a short innovation summary go to the LLM, and the provider policy is shown.
   - Retention can purge old data.
10. **Where do embeddings and reranking run, and what is the latency?**
    - In-process CPU hashing embeddings, pgvector HNSW in Postgres, deterministic rerank in the API process.
    - p50 10 ms and p95 20 ms without an LLM; add the provider latency when one is configured.
11. **How is confidence calculated?**
    - A heuristic weighted sum of six visible signals with penalties (see ARCHITECTURE.md).
    - It is explicitly not calibrated.
12. **Can you determine patentability?**
    - **No.** The system shows overlapping prior art, flags relevant provisions (e.g. s.3(p), 3(d), 3(e)) with their source passages, and routes to IP review.
    - Direct requests get a boundary statement.
13. **Prompt injection from documents?** See Prompt-injection detail above; demonstrated with a seeded malicious upload.
14. **Who curates the corpus?**
    - Each source has a named curator and an update frequency (90–365 days).
    - Admins approve new sources and ingest official documents.
    - Every change is audited.
    - Currently the team is curator.
15. **Cost per query?**
    - Measured from token usage once an LLM key is set (System Health).
    - The assumption is set by `LLM_PRICE_*`. Today it is $0: extractive mode, no API calls.
    - Expected with an LLM: one generation call plus one entailment call per key point, roughly 3–6k tokens per query.
16. **Real refusal case:**
    - "Give me the full TKDL records for Ashwagandha formulations";
    - "What is the Brazilian ANVISA procedure…";
    - "What does the EU require…";
    - "What regulatory category applies to my herbal capsule?" (asks for the market).
17. **Real multilingual case:** "पारंपरिक ज्ञान के पेटेंट के बारे में भारत का कानून क्या कहता है?" (an assistant example card).
18. **Citation click-through:** click any `[n]` chip in an answer. The drawer shows the exact passage, highlighted within the full document, with metadata, URL and why it was retrieved.

## 3. Sustainability & adoption

- **First persona:** R&D teams at Ayurveda MSMEs and startups preparing a new proprietary formulation for India first, with export ambitions. A secondary persona is university/AYUSH-institute IP cells.
- **Curation:**
  - A named curator per source.
  - Statutes are re-checked every 180 days and regulations every 90 days, or immediately when a Gazette notification appears.
  - The Update Queue is the work list.
- **Hosting:**
  - A single institutional deployment: small VM plus managed Postgres/pgvector.
  - The LLM is either an API with a documented data policy or a self-hosted open-weight model through `LLM_BASE_URL` for confidential work.
- **Cost at 10k users:** System Health projects monthly LLM cost from measured average cost per query × 200,000 queries (10k users × 20 queries). Infrastructure is a small VM plus managed Postgres.
- **Adoption path:**
  1. Pilot with 2–3 MSMEs on the curated corpus.
  2. Expand the corpus with verified official texts, replacing the seed summaries.
  3. Run expert-labelled evaluation.
  4. Deploy institutionally with an IP cell as the reviewer-of-record.

## 4. Slide changes (PPT)

- **Slide 2:** show the flow *Hindi/English query → jurisdiction routing → hybrid retrieval → verification → answer or abstention*, and the structured analysis cards. Claim only what is listed as Done above.
- **Slide 3:** show the pipeline diagram from ARCHITECTURE.md with the multilingual branch and the privacy/safety gate. Add the GitHub link.
- **Slide 4:** pair each risk with its implemented mitigation: OCR (Tesseract + confidence gate), version drift (Update Queue + supersession), injection, confidential formulations, TKDL (explicit status), hosting (runtime table), coverage (matrix).
- **Slide 5:** use only the measured before/after comparison: IP-SAKTI vs the BM25 baseline on recall, contamination and abstention. Do not add invented percentages.
- **Slide 6:** add official source links, a Coverage Matrix screenshot, an evaluation screenshot, the TKDL clarification, and the label "real prototype screens".

## 5. Still open (honest list)

- **LLM runs locally via Ollama (free, private).** It was tested live on `llama3.2` (3B): English answers verified SUPPORTED in about 8 s, and Hindi answers are correct but thin. A 7B model is recommended for Hindi quality. Hosted providers (Gemini, Groq, Grok, OpenAI) are one `.env` line away.
- **Seed summaries unverified:** statute summaries must be verified against the official Gazette/regulator text and then marked *Approve (verified)* in the Update Queue.
- **Labels not expert-reviewed:** evaluation and classification labels are author-assigned and need expert review.
- **Embeddings are lexical:** the default hashing embeddings match shared vocabulary rather than meaning; semantic embeddings (OpenAI or bge-m3) require a reseed.
- **No application-level encryption at rest.**
- **English-only OCR:** the Hindi OCR language pack is not installed.
