"""RAG evaluation: runs seeded questions through the live pipeline and computes metrics.

Metrics are computed from actual outputs — nothing is hardcoded.
"""
import math
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from sqlalchemy import text

from app.models.orm import EvaluationQuestion, EvaluationRun, Workspace
from app.seed.corpus import CLASSIFICATION_CASES
from app.services.embeddings import get_embedder
from app.services.governance import _pct
from app.services.llm import LLMError, get_llm
from app.services.regulatory import classify_jurisdiction
from app.services.research import run_research
from app.services.retrieval import content_terms

K = 6
REFUSAL = ("cannot", "can't", "unable", "not able", "insufficient", "don't have", "do not have", "not possible", "no access", "which market")


def _bm25_baseline(db: Session, q: str) -> list[dict]:
    """Keyword-only baseline: plain full-text ranking, no filters, no dense/metadata/graph, no rerank, no safety gate."""
    terms = content_terms(q)
    if not terms:
        return []
    rows = db.execute(text(
        "SELECT d.title, d.jurisdiction FROM document_chunks c JOIN documents d ON d.id = c.document_id "
        "WHERE d.workspace_id IS NULL AND c.search_vector @@ to_tsquery('english', :q) "
        "ORDER BY ts_rank_cd(c.search_vector, to_tsquery('english', :q), 32) DESC LIMIT :k"), {"q": " | ".join(terms[:40]), "k": K}).mappings().all()
    return [dict(r) for r in rows]


def _recall(titles: list[str], expected: list[str]) -> float:
    return sum(1 for e in expected if any(e.lower() in t.lower() for t in titles)) / len(expected)


def _contamination(jurs: list[str], expected_j: str | None) -> float | None:
    if not expected_j or not jurs:
        return None
    return sum(1 for j in jurs if j not in (expected_j, "INTERNATIONAL")) / len(jurs)


def classification_agreement() -> dict:
    agree, total, rows = 0, 0, []
    for key, answers, expected in CLASSIFICATION_CASES:
        for j, exp in expected.items():
            got = (classify_jurisdiction(j, answers)["candidates"] or [{}])[0].get("key")
            total += 1
            agree += got == exp
            rows.append({"case": key, "jurisdiction": j, "expected": exp, "predicted": got, "agree": got == exp})
    return {"cases": len(CLASSIFICATION_CASES), "labels": total, "agreement": round(agree / total, 3) if total else None, "rows": rows,
            "note": "Labels are author-assigned against the seeded pathway definitions and need expert review."}

ABSTAIN_TYPES = {"abstention", "clarification"}


def _hit(title: str, expected: list[str]) -> bool:
    return any(e.lower() in title.lower() for e in expected)


def _ndcg(rels: list[int]) -> float:
    dcg = sum(r / math.log2(i + 2) for i, r in enumerate(rels))
    ideal = sum(r / math.log2(i + 2) for i, r in enumerate(sorted(rels, reverse=True)))
    return dcg / ideal if ideal else 0.0


def run_evaluation(db: Session, workspace_id: str | None = None) -> EvaluationRun:
    if not workspace_id:
        workspace_id = db.execute(select(Workspace.id).limit(1)).scalar()
    questions = db.execute(select(EvaluationQuestion).order_by(EvaluationQuestion.key)).scalars().all()
    results = []
    for q in questions:
        t0 = time.monotonic()
        r = run_research(db, q.question, workspace_id=workspace_id, jurisdiction=q.jurisdiction)
        latency = int((time.monotonic() - t0) * 1000)
        titles = [e["title"] for e in r.get("evidence", [])]
        rels = [1 if _hit(t, q.expected_document_titles) else 0 for t in titles] if q.expected_document_titles else []
        abstained = r["type"] in ABSTAIN_TYPES
        kps = [k for k in r.get("key_points", []) if k["type"] in ("FACT", "INFERENCE")]
        text = (r.get("answer", "") + " " + " ".join(k["text"] for k in kps) + " " + " ".join(e.get("passage", "") for e in r.get("evidence", []))).lower()
        det_j = r["analysis"].get("jurisdictions", [])
        exp_j = q.jurisdiction
        base_rows = _bm25_baseline(db, q.question)
        base_titles = [b["title"] for b in base_rows]
        results.append({
            "key": q.key, "category": q.category, "question": q.question, "type": r["type"], "evidence_status": r["evidence_status"],
            "expected_abstention": q.expected_abstention, "abstained": abstained,
            "abstention_correct": abstained == q.expected_abstention,
            "precision_at_k": round(sum(rels) / len(rels), 3) if rels else None,
            "recall": (1.0 if any(rels) else 0.0) if q.expected_document_titles and not q.expected_abstention else None,
            "ndcg": round(_ndcg(rels), 3) if rels else None,
            "keywords_found": all(k.lower() in text for k in q.expected_keywords) if q.expected_keywords and not abstained else None,
            "citations_valid": all(not k["invalid_citations"] for k in kps) if kps else None,
            "supported_fraction": round(sum(1 for k in kps if k["status"] == "SUPPORTED") / len(kps), 3) if kps else None,
            "unsupported_claims": sum(1 for k in kps if k["status"] in ("UNSUPPORTED", "INSUFFICIENT")),
            "claims": len(kps),
            "jurisdiction_correct": (exp_j in det_j) if exp_j else None,
            "fresh_fraction": round(sum(1 for e in r.get("evidence", []) if e["freshness"] in ("Current", "Recently checked")) / len(r["evidence"]), 3) if r.get("evidence") else None,
            "latency_ms": latency,
            "top_titles": titles[:3],
            "recall_at_k": round(_recall(titles[:K], q.expected_document_titles), 3) if q.expected_document_titles and not q.expected_abstention else None,
            "baseline_recall_at_k": round(_recall(base_titles, q.expected_document_titles), 3) if q.expected_document_titles and not q.expected_abstention else None,
            "contamination": _contamination([e["jurisdiction"] for e in r.get("evidence", [])], exp_j),
            "baseline_contamination": _contamination([b["jurisdiction"] for b in base_rows], exp_j),
        })

    def avg(key):
        vals = [x[key] for x in results if x[key] is not None]
        return round(sum(float(v) for v in vals) / len(vals), 3) if vals else None

    total_claims = sum(x["claims"] for x in results)
    metrics = {
        "questions": len(results),
        "retrieval_precision": avg("precision_at_k"),
        "retrieval_recall": avg("recall"),
        "ndcg": avg("ndcg"),
        "keyword_coverage": avg("keywords_found"),
        "citation_correctness": avg("citations_valid"),
        "citation_entailment": avg("supported_fraction"),
        "unsupported_claim_rate": round(sum(x["unsupported_claims"] for x in results) / total_claims, 3) if total_claims else None,
        "abstention_accuracy": avg("abstention_correct"),
        "jurisdiction_accuracy": avg("jurisdiction_correct"),
        "freshness": avg("fresh_fraction"),
        "avg_latency_ms": int(sum(x["latency_ms"] for x in results) / len(results)) if results else None,
        "passed": sum(1 for x in results if x["abstention_correct"] and x["recall"] != 0.0 and x["keywords_found"] is not False),
        "test_set_size": len(results),
        "k": K,
        "recall_at_k": avg("recall_at_k"),
        "jurisdiction_contamination": avg("contamination"),
        "latency_p50_ms": _pct([x["latency_ms"] for x in results], 0.5),
        "latency_p95_ms": _pct([x["latency_ms"] for x in results], 0.95),
    }
    expected_answerable = sum(1 for x in results if not x["expected_abstention"]) / len(results) if results else None
    baselines = {
        "bm25_keyword_only": {
            "description": "Plain full-text ranking over the same corpus: no jurisdiction filter, dense/metadata/graph retrieval, reranking, verification or safety gate.",
            "recall_at_k": avg("baseline_recall_at_k"),
            "jurisdiction_contamination": avg("baseline_contamination"),
            "abstention_accuracy": round(expected_answerable, 3) if expected_answerable is not None else None,
            "citation_verification": "none",
        },
        "always_answer": {
            "description": "Same retrieval but no abstention/safety gate: answers every question.",
            "abstention_accuracy": round(expected_answerable, 3) if expected_answerable is not None else None,
        },
    }
    llm = get_llm()
    if llm.available:
        refusals_ok, n = 0, 0
        for q in questions:
            try:
                ans = llm.complete("Answer the question briefly.", q.question, max_tokens=200).lower()
            except LLMError:
                continue
            n += 1
            refusals_ok += any(w in ans for w in REFUSAL) == q.expected_abstention
        baselines["llm_only_no_retrieval"] = {
            "description": f"{llm.name} answering directly, without retrieval or verification.",
            "abstention_accuracy": round(refusals_ok / n, 3) if n else None,
            "answers_with_verifiable_citations": 0.0,
            "questions": n,
        }
    else:
        baselines["llm_only_no_retrieval"] = {"description": "Not run — no LLM configured (set LLM_PROVIDER and LLM_API_KEY).", "abstention_accuracy": None}
    metrics["baselines"] = baselines
    metrics["classification"] = classification_agreement()
    run = EvaluationRun(metrics=metrics, results=results, llm_provider=get_llm().name, embedding_provider=get_embedder().name)
    db.add(run)
    db.flush()
    return run
