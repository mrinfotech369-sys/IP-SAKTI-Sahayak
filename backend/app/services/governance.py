"""Coverage matrix, provision map, corpus lifecycle, retention and runtime metrics.

Everything here is computed from the database — no placeholder numbers.
"""
from datetime import datetime, timedelta, timezone
from statistics import median

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.orm import Conversation, Document, DocumentChunk, Innovation, Message, Source, Workspace
from app.services.profile import DISEASE_WORDS
from app.services.terminology import TerminologyEngine

JURISDICTIONS = [("IN", "India"), ("US", "USA"), ("EU", "European Union"), ("AU", "Australia"), ("INTERNATIONAL", "International")]
DOMAINS = [("IP", "IP / patent law"), ("TK_ABS", "Traditional knowledge & ABS"), ("REGULATORY", "Regulatory"), ("SCIENTIFIC", "Scientific evidence")]
REAL_REVIEW = ("SEED_SUMMARY", "UPLOADED_OFFICIAL", "VERIFIED")


# ---------------------------------------------------------------------------
# Coverage matrix
# ---------------------------------------------------------------------------

def coverage(db: Session) -> dict:
    rows = db.execute(
        select(Document.jurisdiction, Document.domain, Document.review_status, Document.title, Document.document_type, Source.authority_tier,
               func.count(DocumentChunk.id))
        .join(Source, Source.id == Document.source_id)
        .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
        .where(Document.workspace_id.is_(None))
        .group_by(Document.id, Source.authority_tier)
    ).all()
    cells: dict = {}
    for jur, dom, review, title, dtype, tier, chunks in rows:
        c = cells.setdefault((jur, dom), {"documents": 0, "chunks": 0, "real": 0, "demo": 0, "official": 0, "titles": []})
        c["documents"] += 1
        c["chunks"] += chunks
        if review in REAL_REVIEW:
            c["real"] += 1
            if tier <= 2:
                c["official"] += 1
        else:
            c["demo"] += 1
        c["titles"].append({"title": title, "type": dtype, "review_status": review, "tier": tier})

    matrix = []
    for j, jname in JURISDICTIONS:
        row = {"jurisdiction": j, "name": jname, "cells": {}}
        for d, _ in DOMAINS:
            c = cells.get((j, d), {"documents": 0, "chunks": 0, "real": 0, "demo": 0, "official": 0, "titles": []})
            if c["official"] >= 2 or (d == "SCIENTIFIC" and c["real"] >= 3):
                status = "Built"
            elif c["documents"]:
                status = "Partial"
            else:
                status = "Planned"
            if d == "SCIENTIFIC" and j not in ("INTERNATIONAL",):
                status = "N/A"  # science is indexed internationally, not per country
            note = None
            if status == "Partial" and c["real"] == 0:
                note = "Only demo/fictional records — not real coverage."
            if j == "EU":
                note = "Not ingested. EU rules are out of scope for this MVP; questions about the EU are refused."
            row["cells"][d] = {**c, "status": status, "note": note}
        matrix.append(row)

    totals = db.execute(
        select(func.count(Document.id), func.count(func.distinct(Document.source_id))).where(Document.workspace_id.is_(None))
    ).one()
    chunks = db.scalar(select(func.count(DocumentChunk.id)).join(Document).where(Document.workspace_id.is_(None)))
    demo = db.scalar(select(func.count(Document.id)).where(Document.workspace_id.is_(None), Document.is_demo.is_(True)))
    return {
        "matrix": matrix,
        "domains": [{"key": k, "name": n} for k, n in DOMAINS],
        "corpus": {"documents": totals[0], "sources": totals[1], "chunks": chunks, "demo_documents": demo, "real_documents": totals[0] - demo},
        "legend": {
            "Built": "At least two real Tier 1–2 documents ingested (scientific: three real studies).",
            "Partial": "Some documents ingested, but coverage is incomplete or only demo.",
            "Planned": "Nothing ingested; the system will not answer from this cell.",
            "N/A": "Not applicable (scientific literature is indexed internationally).",
        },
    }


# ---------------------------------------------------------------------------
# Provision map (decision support — relevance flags, never legal determinations)
# ---------------------------------------------------------------------------

PROVISIONS = [
    # id, jurisdiction, area, instrument, provision, doc_key, issue, trigger
    ("IN-PA-3p", "IN", "IP", "Patents Act, 1970", "Section 3(p)", "in_patents_act_s3",
     "Inventions that are in effect traditional knowledge, or aggregations/duplications of known properties of traditional components, are not inventions.", "classical"),
    ("IN-PA-3d", "IN", "IP", "Patents Act, 1970", "Section 3(d)", "in_patents_act_s3",
     "New forms (extracts, complexes, particle size…) of known substances need significantly enhanced efficacy.", "process"),
    ("IN-PA-3e", "IN", "IP", "Patents Act, 1970", "Section 3(e)", "in_patents_act_s3",
     "Mere admixtures that only aggregate component properties are excluded; synergy must be shown.", "multi"),
    ("IN-PA-10", "IN", "IP", "Patents Act, 1970", "Section 10(4)(ii)(D)", "in_patents_act_s10_25",
     "Specification must disclose source and geographical origin of biological material.", "botanical"),
    ("IN-PA-25", "IN", "IP", "Patents Act, 1970", "Section 25(1)(j),(k)", "in_patents_act_s10_25",
     "Pre-grant opposition on non-disclosure of origin or anticipation by local/indigenous knowledge.", "botanical"),
    ("IN-BD-6", "IN", "TK_ABS", "Biological Diversity Act, 2002 (am. 2023)", "Section 6", "in_bd_act_s6",
     "NBA approval for IPR based on Indian biological resources (before grant); possible benefit sharing.", "india_source"),
    ("IN-BD-3-7", "IN", "TK_ABS", "Biological Diversity Act, 2002 (am. 2023)", "Sections 3 and 7", "in_bd_act_s3_7",
     "Access/commercial-utilisation obligations (NBA for foreign-controlled entities; SBB intimation for Indian entities).", "india_source"),
    ("IN-DCA-3", "IN", "REGULATORY", "Drugs and Cosmetics Act, 1940", "Section 3(a), 3(h)", "in_dca_s3",
     "Whether the product is a classical ASU drug or a patent/proprietary ASU medicine.", "market_in"),
    ("IN-DR-158B", "IN", "REGULATORY", "Drugs Rules, 1945", "Rule 158B", "in_rule_158b",
     "Licensing data: textual rationale, effectiveness evidence and safety data by category.", "market_in"),
    ("IN-DR-SchT", "IN", "REGULATORY", "Drugs Rules, 1945", "Schedule T", "in_schedule_t", "GMP for ASU manufacturing.", "market_in"),
    ("IN-DMR-3", "IN", "REGULATORY", "Drugs and Magic Remedies Act, 1954", "Section 3", "in_dmr_act",
     "Advertising a drug for scheduled diseases is prohibited.", "disease_in"),
    ("US-321ff", "US", "REGULATORY", "FD&C Act", "21 U.S.C. 321(ff)", "us_dshea_321ff", "Dietary supplement definition.", "market_us"),
    ("US-101.93", "US", "REGULATORY", "21 CFR", "101.93", "us_cfr_101_93",
     "Structure/function claims: 30-day notification, mandatory disclaimer, no disease claims.", "claims_us"),
    ("US-321g", "US", "REGULATORY", "FD&C Act", "21 U.S.C. 321(g)(1)", "us_drug_definition",
     "Disease claims make the product a drug (IND/NDA pathway).", "disease_us"),
    ("US-350b", "US", "REGULATORY", "FD&C Act", "21 U.S.C. 350b (NDI)", "us_ndi",
     "New dietary ingredient notification 75 days before marketing; novel processing may matter.", "process_us"),
    ("US-111", "US", "REGULATORY", "21 CFR", "Part 111", "us_cgmp_111", "Dietary supplement cGMP incl. botanical identity testing.", "market_us"),
    ("AU-26A", "AU", "REGULATORY", "Therapeutic Goods Act 1989", "Section 26A / ARTG", "au_tg_act_listing",
     "Listing requires permitted ingredients, permitted indications and sponsor-held evidence.", "market_au"),
    ("AU-PI", "AU", "REGULATORY", "Permissible Indications Determination", "Permissible indications", "au_permissible_indications",
     "Listed medicines may only use permitted indications; traditional indications must name the tradition.", "claims_au"),
    ("AU-REG", "AU", "REGULATORY", "Registered complementary medicines", "AUST R", "au_registered_cm",
     "High-level (disease) indications require registration and TGA evaluation.", "disease_au"),
    ("INT-WIPO-3", "INTERNATIONAL", "IP", "WIPO GR/ATK Treaty (2024)", "Article 3", "wipo_gr_atk_treaty",
     "Disclosure of origin for patent applications based on genetic resources / associated TK.", "botanical"),
    ("INT-NP-5-7", "INTERNATIONAL", "TK_ABS", "Nagoya Protocol", "Articles 5, 7", "nagoya_protocol",
     "Benefit sharing and prior informed consent for genetic resources and associated TK.", "botanical"),
]


def provision_map(db: Session, inn: Innovation) -> dict:
    p = inn.profile
    markets = set(inn.target_markets or [])
    ingredients = (p.ingredients if p else []) or []
    claims = " ".join((p.claims if p else []) or []) + " " + ((p.intended_use or "") if p else "")
    matches = TerminologyEngine(db).normalize(" ".join(i.get("name", "") for i in ingredients))
    classical = [m.canonical for m in matches if m.domain in ("BOTANICAL", "FORMULATION")]
    disease = bool(DISEASE_WORDS.search(claims))
    process = bool(p and (p.extraction_method or p.process))
    india_source = "IN" in markets or any("india" in (i.get("source") or "").lower() for i in ingredients)
    reasons = {
        "classical": (bool(classical), f"Uses classical Ayurvedic ingredient(s): {', '.join(classical)}."),
        "process": (process, "Profile includes an extraction/processing step producing an extract or complex."),
        "multi": (len(ingredients) >= 2, f"Combines {len(ingredients)} ingredients."),
        "botanical": (bool(ingredients), "Invention uses biological (botanical) material."),
        "india_source": (india_source, "Biological resources appear to be sourced from India / India is a target market."),
        "market_in": ("IN" in markets, "India is a target market."),
        "disease_in": ("IN" in markets and disease, "India market with a disease-type claim."),
        "market_us": ("US" in markets, "USA is a target market."),
        "claims_us": ("US" in markets and bool(p and p.claims), "USA market with proposed label claims."),
        "disease_us": ("US" in markets and disease, "USA market with a disease-type claim."),
        "process_us": ("US" in markets and process, "USA market with a novel extraction/processing step."),
        "market_au": ("AU" in markets, "Australia is a target market."),
        "claims_au": ("AU" in markets and bool(p and p.claims), "Australia market with proposed indications."),
        "disease_au": ("AU" in markets and disease, "Australia market with a disease-type indication."),
    }
    docs = {d.metadata_.get("key"): d for d in db.execute(select(Document).where(Document.workspace_id.is_(None))).scalars() if d.metadata_.get("key")}
    items = []
    for pid, jur, area, instrument, provision, key, issue, trig in PROVISIONS:
        hit, why = reasons[trig]
        if not hit:
            continue
        d = docs.get(key)
        items.append({
            "id": pid, "jurisdiction": jur, "area": area, "instrument": instrument, "provision": provision, "issue": issue,
            "why_flagged": why, "document_id": d.id if d else None, "document_title": d.title if d else None,
            "review_status": d.review_status if d else "NOT_INGESTED",
            "severity": "HIGH" if trig in ("classical", "disease_in", "disease_us", "disease_au") else "MEDIUM" if trig in ("process", "multi", "india_source", "process_us") else "INFO",
        })
    order = {"HIGH": 0, "MEDIUM": 1, "INFO": 2}
    items.sort(key=lambda x: (order[x["severity"]], x["jurisdiction"], x["id"]))
    return {"provisions": items, "boundary": "Relevance flags for professional review — not a determination of patentability, infringement or regulatory status."}


# ---------------------------------------------------------------------------
# Corpus lifecycle
# ---------------------------------------------------------------------------

def update_status(last_checked, frequency_days: int, superseded: bool = False) -> str:
    if superseded:
        return "Superseded"
    if not last_checked:
        return "Never checked"
    age = (datetime.now(timezone.utc) - last_checked).days
    if age <= frequency_days:
        return "Up to date"
    if age <= frequency_days * 2:
        return "Review due"
    return "Overdue"


def update_queue(db: Session) -> list[dict]:
    out = []
    for d in db.execute(select(Document).where(Document.workspace_id.is_(None))).scalars():
        s = d.source
        st = update_status(d.last_checked, s.update_frequency_days, bool(d.superseded_by_document_id))
        if st in ("Up to date",):
            continue
        age = (datetime.now(timezone.utc) - d.last_checked).days if d.last_checked else None
        out.append({"document_id": d.id, "title": d.title, "source": s.name, "curator": s.curator, "jurisdiction": d.jurisdiction,
                    "last_checked": d.last_checked.isoformat() if d.last_checked else None, "age_days": age,
                    "frequency_days": s.update_frequency_days, "update_status": st, "review_status": d.review_status,
                    "version": d.version, "effective_date": d.effective_date})
    rank = {"Overdue": 0, "Never checked": 1, "Review due": 2, "Superseded": 3}
    out.sort(key=lambda x: (rank[x["update_status"]], -(x["age_days"] or 0)))
    return out


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------

RETENTION_DAYS = {"RETAIN_90_DAYS": 90, "RETAIN_365_DAYS": 365, "RETAIN_INDEFINITELY": None}


def purge_expired(db: Session, dry_run: bool = True) -> dict:
    """Delete conversations and workspace uploads older than each workspace's retention policy.

    Audit logs are kept (they contain no confidential text)."""
    report = []
    for w in db.execute(select(Workspace)).scalars():
        days = RETENTION_DAYS.get(w.retention_policy)
        if not days:
            continue
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        conv_q = select(Conversation.id).where(Conversation.workspace_id == w.id, Conversation.updated_at < cutoff)
        doc_q = select(Document.id).where(Document.workspace_id == w.id, Document.created_at < cutoff)
        n_conv = len(db.execute(conv_q).all())
        n_doc = len(db.execute(doc_q).all())
        if not dry_run:
            db.execute(delete(Conversation).where(Conversation.id.in_(conv_q)))
            db.execute(delete(Document).where(Document.id.in_(doc_q)))
        report.append({"workspace": w.name, "policy": w.retention_policy, "cutoff": cutoff.isoformat(),
                       "conversations": n_conv, "uploaded_documents": n_doc})
    return {"dry_run": dry_run, "workspaces": report}


# ---------------------------------------------------------------------------
# Runtime metrics
# ---------------------------------------------------------------------------

def _pct(vals: list[int], q: float):
    if not vals:
        return None
    s = sorted(vals)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def runtime_metrics(db: Session, limit: int = 500) -> dict:
    payloads = db.execute(select(Message.payload).where(Message.role == "assistant").order_by(Message.created_at.desc()).limit(limit)).scalars().all()
    lat = [p.get("trace", {}).get("latency_ms") for p in payloads if p and p.get("trace", {}).get("latency_ms") is not None]
    usage = [p.get("generation", {}).get("usage") or {} for p in payloads if p]
    costs = [u.get("estimated_cost_usd", 0.0) for u in usage]
    llm_calls = [u.get("calls", 0) for u in usage]
    avg_cost = (sum(costs) / len(costs)) if costs else 0.0
    return {
        "queries_sampled": len(payloads),
        "latency_ms": {"p50": _pct(lat, 0.5), "p95": _pct(lat, 0.95), "median": median(lat) if lat else None, "max": max(lat) if lat else None},
        "llm_calls_per_query": round(sum(llm_calls) / len(llm_calls), 2) if llm_calls else 0,
        "avg_cost_per_query_usd": round(avg_cost, 6),
        "cost_assumptions": {"input_per_million_usd": settings.LLM_PRICE_INPUT_PER_M, "output_per_million_usd": settings.LLM_PRICE_OUTPUT_PER_M,
                             "provider": settings.LLM_PROVIDER},
        "projection_10k_users": {
            "assumption": "10,000 users × 20 queries/month",
            "monthly_queries": 200_000,
            "monthly_llm_cost_usd": round(avg_cost * 200_000, 2),
        },
        "runtime": {
            "retrieval": "In-process in the FastAPI worker: pgvector HNSW + GIN full-text queries inside PostgreSQL (CPU).",
            "embeddings": f"{settings.EMBEDDING_PROVIDER} ({'in-process CPU, no network' if settings.EMBEDDING_PROVIDER == 'hashing' else 'external/managed'})",
            "reranking": "Deterministic scoring in-process (no cross-encoder model).",
            "generation": f"{settings.LLM_PROVIDER} ({'local (Ollama, on this machine)' if settings.LLM_PROVIDER == 'ollama' else 'external API' if settings.LLM_PROVIDER in ('openai', 'deepseek', 'grok', 'gemini', 'groq') else 'none — extractive'})",
            "ingestion": "Background task off the request path (FastAPI BackgroundTasks); OCR via Tesseract when available.",
        },
    }
