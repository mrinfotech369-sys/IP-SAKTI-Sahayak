"""Hybrid retrieval over Postgres: pgvector (dense) + tsvector (lexical) +
metadata + graph expansion, then dedupe and deterministic reranking.

Every call returns a full trace so answers can be reconstructed later.
"""
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.embeddings import get_embedder

STOPWORDS = set(
    """a an the of and or for to in on at by with from is are was were be been being this that these those it its
    as into about what which who whom how why when where can could should would will may might must do does did
    my our your their his her i we you they me us them any some all not no yes than then there here also such
    under over per via vs versus between product products""".split()
)

TIER_AUTHORITY = {1: 1.0, 2: 0.85, 3: 0.7, 4: 0.5, 5: 0.3}

INTENT_DOC_TYPES = {
    "REGULATORY": {"LEGISLATION", "RULES", "GUIDANCE", "REGULATION"},
    "PRODUCT_CLASSIFICATION": {"LEGISLATION", "RULES", "GUIDANCE", "REGULATION"},
    "JURISDICTION_COMPARISON": {"LEGISLATION", "RULES", "GUIDANCE", "REGULATION"},
    "PATENT_SEARCH": {"PATENT", "LEGISLATION", "GUIDANCE"},
    "PRIOR_ART_SEARCH": {"PATENT"},
    "SCIENTIFIC_EVIDENCE": {"STUDY", "MONOGRAPH"},
    "TRADITIONAL_KNOWLEDGE": {"TK_CONTEXT", "LEGISLATION", "GUIDANCE"},
}

INTENT_DOMAINS = {
    "REGULATORY": {"REGULATORY"},
    "PRODUCT_CLASSIFICATION": {"REGULATORY"},
    "JURISDICTION_COMPARISON": {"REGULATORY"},
    "PATENT_SEARCH": {"IP"},
    "PRIOR_ART_SEARCH": {"IP"},
    "SCIENTIFIC_EVIDENCE": {"SCIENTIFIC"},
    "TRADITIONAL_KNOWLEDGE": {"TK_ABS"},
}


def content_terms(q: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", q.lower())
    out: list[str] = []
    for t in toks:
        if len(t) > 2 and t not in STOPWORDS and t not in out:
            out.append(t)
    return out


def freshness_status(last_checked: Optional[datetime], superseded: bool) -> str:
    if superseded:
        return "Superseded"
    if not last_checked:
        return "Unknown"
    age = (datetime.now(timezone.utc) - last_checked).days
    if age <= 30:
        return "Current"
    if age <= 180:
        return "Recently checked"
    return "Potentially stale"


@dataclass
class RetrievalFilters:
    jurisdictions: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    document_types: list[str] = field(default_factory=list)
    max_tier: Optional[int] = None
    language: Optional[str] = None
    include_superseded: bool = False
    workspace_id: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _filter_sql(f: RetrievalFilters, params: dict) -> str:
    clauses = ["s.active = true", "d.access_level <> 'RESTRICTED'", "d.review_status <> 'REJECTED'"]
    if f.workspace_id:
        clauses.append("(d.workspace_id IS NULL OR d.workspace_id = :ws)")
        params["ws"] = f.workspace_id
    else:
        clauses.append("d.workspace_id IS NULL")
    if f.jurisdictions:
        # International instruments apply alongside national ones.
        clauses.append("d.jurisdiction = ANY(:jurs)")
        params["jurs"] = list(f.jurisdictions) + ["INTERNATIONAL"]
    if f.domains:
        clauses.append("d.domain = ANY(:domains)")
        params["domains"] = f.domains
    if f.document_types:
        clauses.append("d.document_type = ANY(:dtypes)")
        params["dtypes"] = f.document_types
    if f.max_tier:
        clauses.append("s.authority_tier <= :max_tier")
        params["max_tier"] = f.max_tier
    if f.language:
        clauses.append("d.language = :lang")
        params["lang"] = f.language
    if not f.include_superseded:
        clauses.append("d.superseded_by_document_id IS NULL")
    if f.date_from:
        clauses.append("coalesce(d.publication_date, '') >= :dfrom")
        params["dfrom"] = f.date_from
    if f.date_to:
        clauses.append("coalesce(d.publication_date, '9999') <= :dto")
        params["dto"] = f.date_to
    return " AND ".join(clauses)


_SELECT = """
    c.id AS chunk_id, c.document_id, c.content, c.section, c.subsection, c.chunk_type, c.page_number,
    c.injection_flag, c.metadata AS chunk_meta,
    d.title, d.document_type, d.domain, d.jurisdiction, d.publication_date, d.effective_date, d.last_checked,
    d.version, d.url, d.language, d.is_demo, d.review_status, d.superseded_by_document_id, d.metadata AS doc_meta,
    s.name AS source_name, s.authority, s.authority_tier AS tier, s.id AS source_id
"""
_FROM = "FROM document_chunks c JOIN documents d ON d.id = c.document_id JOIN sources s ON s.id = d.source_id"


def _dense(db: Session, vec: list[float], f: RetrievalFilters, limit: int) -> list[dict]:
    params: dict[str, Any] = {"vec": str(vec), "lim": limit}
    where = _filter_sql(f, params)
    rows = db.execute(
        text(
            f"SELECT {_SELECT}, 1 - (c.embedding <=> CAST(:vec AS vector)) AS dense "
            f"{_FROM} WHERE {where} AND c.embedding IS NOT NULL ORDER BY c.embedding <=> CAST(:vec AS vector) LIMIT :lim"
        ),
        params,
    ).mappings().all()
    return [dict(r) for r in rows]


def _lexical(db: Session, terms: list[str], f: RetrievalFilters, limit: int) -> list[dict]:
    if not terms:
        return []
    params: dict[str, Any] = {"tsq": " | ".join(terms[:40]), "lim": limit}
    where = _filter_sql(f, params)
    rows = db.execute(
        text(
            f"SELECT {_SELECT}, ts_rank_cd(c.search_vector, to_tsquery('english', :tsq), 32) AS lexical "
            f"{_FROM} WHERE {where} AND c.search_vector @@ to_tsquery('english', :tsq) "
            f"ORDER BY lexical DESC LIMIT :lim"
        ),
        params,
    ).mappings().all()
    return [dict(r) for r in rows]


def _metadata(db: Session, keywords: list[str], f: RetrievalFilters, limit: int) -> list[dict]:
    kws = [k.lower() for k in keywords if k]
    if not kws:
        return []
    params: dict[str, Any] = {"kws": kws, "lim": limit}
    where = _filter_sql(f, params)
    rows = db.execute(
        text(
            f"SELECT {_SELECT} {_FROM} WHERE {where} AND c.chunk_index = 0 AND EXISTS ("
            f"SELECT 1 FROM jsonb_array_elements_text(coalesce(d.metadata->'keywords','[]'::jsonb)) k "
            f"WHERE lower(k) = ANY(:kws)) LIMIT :lim"
        ),
        params,
    ).mappings().all()
    return [dict(r) for r in rows]


def _graph(db: Session, doc_ids: list[str], f: RetrievalFilters, limit: int) -> list[dict]:
    """One-hop expansion along curated document relations (metadata.related)."""
    if not doc_ids:
        return []
    params: dict[str, Any] = {"ids": doc_ids, "lim": limit}
    where = _filter_sql(f, params)
    rows = db.execute(
        text(
            f"SELECT {_SELECT}, src.id AS via_document FROM documents src "
            f"JOIN jsonb_array_elements_text(coalesce(src.metadata->'related','[]'::jsonb)) rel ON true "
            f"JOIN documents d ON d.metadata->>'key' = rel "
            f"JOIN document_chunks c ON c.document_id = d.id AND c.chunk_index = 0 "
            f"JOIN sources s ON s.id = d.source_id "
            f"WHERE src.id = ANY(:ids) AND {where} LIMIT :lim"
        ),
        params,
    ).mappings().all()
    return [dict(r) for r in rows]


@dataclass
class RetrievalOutput:
    results: list[dict]
    candidates: list[dict]
    trace: dict
    sufficient: bool


def retrieve(
    db: Session,
    query: str,
    *,
    expansions: Optional[list[str]] = None,
    filters: Optional[RetrievalFilters] = None,
    intent: str = "GENERAL_INFORMATION",
    feature_terms: Optional[list[str]] = None,
    top_k: Optional[int] = None,
    per_document: int = 2,
    min_score: Optional[float] = None,
) -> RetrievalOutput:
    started = time.monotonic()
    f = filters or RetrievalFilters()
    top_k = top_k or settings.RETRIEVAL_TOP_K
    n = settings.RETRIEVAL_CANDIDATES
    expansions = expansions or []

    q_terms = content_terms(query)
    exp_terms = [t for e in expansions for t in content_terms(e) if t not in q_terms]
    lexical_terms = q_terms + exp_terms
    dense_text = query + (" | " + "; ".join(expansions) if expansions else "")
    embedder = get_embedder()
    vec = embedder.embed_text(dense_text)

    t0 = time.monotonic()
    dense = _dense(db, vec, f, n)
    lexical = _lexical(db, lexical_terms, f, n)
    meta = _metadata(db, [*q_terms, *[e.lower() for e in expansions]], f, 8)
    t1 = time.monotonic()

    pool: dict[str, dict] = {}

    def add(rows: list[dict], method: str) -> None:
        for r in rows:
            cur = pool.setdefault(r["chunk_id"], {**r, "methods": [], "dense": None, "lexical": 0.0})
            if method not in cur["methods"]:
                cur["methods"].append(method)
            if r.get("dense") is not None:
                cur["dense"] = float(r["dense"])
            if r.get("lexical") is not None:
                cur["lexical"] = max(cur["lexical"], float(r["lexical"]))

    add(dense, "DENSE")
    add(lexical, "BM25")
    add(meta, "METADATA")
    seed_docs = list({r["document_id"] for r in sorted(pool.values(), key=lambda r: -(r["lexical"] or 0))[:5]})
    graph = _graph(db, seed_docs, f, 6)
    add(graph, "GRAPH")

    # Dense scores for rows that came only from lexical/metadata/graph.
    missing = [cid for cid, r in pool.items() if r["dense"] is None]
    if missing:
        rows = db.execute(
            text("SELECT id, 1 - (embedding <=> CAST(:vec AS vector)) AS dense FROM document_chunks WHERE id = ANY(:ids)"),
            {"vec": str(vec), "ids": missing},
        ).all()
        for cid, d in rows:
            pool[cid]["dense"] = float(d or 0)

    lex_max = max([r["lexical"] for r in pool.values()] or [0]) or 1.0
    wanted_types = INTENT_DOC_TYPES.get(intent, set())
    wanted_domains = INTENT_DOMAINS.get(intent, set())
    feats = [ft.lower() for ft in (feature_terms or []) if ft]

    scored = []
    for r in pool.values():
        body = f"{r['title']} {r['section'] or ''} {r['content']}".lower()
        coverage = (sum(1 for t in q_terms if t in body) / len(q_terms)) if q_terms else 0.0
        exp_hit = any(e.lower() in body for e in expansions)
        dense_s = max(0.0, r["dense"] or 0.0)
        lex_s = (r["lexical"] or 0.0) / lex_max
        relevance = 0.45 * min(1.0, dense_s * 2.2) + 0.40 * coverage + 0.15 * (1.0 if exp_hit else 0.0)
        jur_match = 1.0 if not f.jurisdictions else (1.0 if r["jurisdiction"] in f.jurisdictions else 0.6)
        authority = TIER_AUTHORITY.get(int(r["tier"]), 0.3)
        fresh = freshness_status(r["last_checked"], bool(r["superseded_by_document_id"]))
        fresh_s = {"Current": 1.0, "Recently checked": 0.85, "Potentially stale": 0.5, "Unknown": 0.4, "Superseded": 0.1}[fresh]
        type_s = 1.0 if (r["document_type"] in wanted_types or r["domain"] in wanted_domains) else (0.6 if not wanted_types else 0.3)
        feat_s = (sum(1 for ft in feats if ft in body) / len(feats)) if feats else 0.0
        rerank = (
            0.40 * relevance
            + 0.15 * lex_s
            + 0.12 * jur_match
            + 0.12 * authority
            + 0.06 * fresh_s
            + 0.10 * type_s
            + 0.05 * feat_s
        )
        if "GRAPH" in r["methods"] and len(r["methods"]) == 1:
            rerank *= 0.85
        if r["injection_flag"]:
            rerank *= 0.6  # untrusted, instruction-bearing text never outranks clean sources
        why = []
        if coverage:
            why.append(f"matches {round(coverage * 100)}% of query terms")
        if exp_hit:
            why.append("matches expanded terminology")
        if int(r["tier"]) == 1:
            why.append(f"Tier 1 official {r['authority']} source")
        if f.jurisdictions and r["jurisdiction"] in f.jurisdictions:
            why.append(f"jurisdiction match ({r['jurisdiction']})")
        if r["document_type"] in wanted_types:
            why.append(f"{r['document_type'].lower().replace('_', ' ')} relevant to {intent.lower().replace('_', ' ')}")
        if "GRAPH" in r["methods"]:
            why.append("linked from a related top-ranked document")
        if r["injection_flag"]:
            why.append("WARNING: contains instruction-like text (treated as data)")
        scored.append(
            {
                "chunk_id": r["chunk_id"],
                "document_id": r["document_id"],
                "source_id": r["source_id"],
                "title": r["title"],
                "source_name": r["source_name"],
                "authority": r["authority"],
                "tier": int(r["tier"]),
                "jurisdiction": r["jurisdiction"],
                "domain": r["domain"],
                "document_type": r["document_type"],
                "section": r["section"],
                "subsection": r["subsection"],
                "chunk_type": r["chunk_type"],
                "content": r["content"],
                "page_number": r["page_number"],
                "url": r["url"],
                "publication_date": r["publication_date"],
                "effective_date": r["effective_date"],
                "last_checked": r["last_checked"].isoformat() if r["last_checked"] else None,
                "version": r["version"],
                "language": r["language"],
                "freshness": fresh,
                "is_demo": bool(r["is_demo"]),
                "review_status": r["review_status"],
                "injection_flag": bool(r["injection_flag"]),
                "methods": r["methods"],
                "dense_score": round(dense_s, 4),
                "lexical_score": round(lex_s, 4),
                "relevance": round(relevance, 4),
                "rerank_score": round(rerank, 4),
                "why_retrieved": "; ".join(why) or "semantic similarity to the query",
            }
        )

    scored.sort(key=lambda x: -x["rerank_score"])
    # Deduplicate: identical content, and at most `per_document` chunks per document.
    seen_content: set[str] = set()
    per_doc: dict[str, int] = {}
    results = []
    for r in scored:
        sig = re.sub(r"\s+", " ", r["content"].lower())[:160]
        if sig in seen_content:
            continue
        if per_doc.get(r["document_id"], 0) >= per_document:
            continue
        if r["relevance"] < (settings.MIN_EVIDENCE_SCORE if min_score is None else min_score):
            continue
        seen_content.add(sig)
        per_doc[r["document_id"]] = per_doc.get(r["document_id"], 0) + 1
        results.append(r)
        if len(results) >= top_k:
            break

    trace = {
        "query": query,
        "query_terms": q_terms,
        "expanded_terms": expansions,
        "filters": f.to_dict(),
        "intent": intent,
        "embedding_provider": embedder.name,
        "counts": {"dense": len(dense), "bm25": len(lexical), "metadata": len(meta), "graph": len(graph), "merged": len(pool)},
        "reranking": "deterministic: relevance, lexical, jurisdiction, authority tier, freshness, document type, feature match",
        "candidates": [
            {k: c[k] for k in ("chunk_id", "title", "section", "methods", "dense_score", "lexical_score", "relevance", "rerank_score")}
            for c in scored[:15]
        ],
        "selected": [r["chunk_id"] for r in results],
        "min_evidence_score": settings.MIN_EVIDENCE_SCORE,
        "search_latency_ms": int((t1 - t0) * 1000),
        "latency_ms": int((time.monotonic() - started) * 1000),
    }
    return RetrievalOutput(results=results, candidates=scored, trace=trace, sufficient=bool(results))
