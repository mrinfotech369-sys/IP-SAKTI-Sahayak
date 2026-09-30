"""Patent / prior-art intelligence: feature-to-document matching and family grouping.

Language policy: overlap is reported as overlap. Never state that a document
makes the innovation unpatentable; professional review is always required.
"""
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.orm import FeatureType, Innovation, Patent, PatentFeatureMatch
from app.services.retrieval import RetrievalFilters, content_terms, retrieve
from app.services.terminology import TerminologyEngine

REVIEW_NOTE = (
    "This document contains features that overlap with the selected innovation feature. "
    "Professional review is required to determine legal significance."
)

MATCHABLE = {
    FeatureType.INGREDIENT: "COMPOSITION",
    FeatureType.COMPOSITION: "COMPOSITION",
    FeatureType.PROCESS: "PROCESS",
    FeatureType.EXTRACTION: "EXTRACTION",
    FeatureType.DELIVERY: "DELIVERY",
    FeatureType.DOSAGE_FORM: "DOSAGE_FORM",
    FeatureType.CLAIM: "CLAIM",
}
MIN_MATCH = 0.3


def _patent_by_doc(db: Session, doc_ids: list[str]) -> dict[str, Patent]:
    if not doc_ids:
        return {}
    rows = db.execute(select(Patent).where(Patent.document_id.in_(doc_ids))).scalars().all()
    return {p.document_id: p for p in rows}


def patent_card(p: Patent, extra: Optional[dict] = None) -> dict:
    d = p.document
    return {
        "patent_id": p.id,
        "document_id": p.document_id,
        "title": p.title,
        "publication_number": p.publication_number,
        "application_number": p.application_number,
        "applicant": p.applicant,
        "inventors": p.inventor,
        "jurisdiction": p.jurisdiction,
        "priority_date": p.priority_date,
        "filing_date": p.filing_date,
        "publication_date": p.publication_date,
        "status": p.status,
        "classification_codes": p.classification_codes,
        "patent_family_id": p.patent_family_id,
        "abstract": p.abstract,
        "claims": p.claims,
        "is_demo": d.is_demo if d else True,
        "review_status": d.review_status if d else "DEMO_FICTIONAL",
        "source": d.source.name if d and d.source else None,
        "human_review_required": True,
        "review_note": REVIEW_NOTE,
        **(extra or {}),
    }


def group_by_family(cards: list[dict]) -> list[dict]:
    fams: dict[str, dict] = {}
    for c in cards:
        fid = c.get("patent_family_id") or c["publication_number"]
        fam = fams.setdefault(fid, {"family_id": fid, "members": [], "best_score": 0.0, "matched_features": set()})
        fam["members"].append(c)
        fam["best_score"] = max(fam["best_score"], c.get("similarity_score") or 0.0)
        for mf in c.get("matched_features", []):
            fam["matched_features"].add(mf)
    out = []
    for fam in fams.values():
        fam["matched_features"] = sorted(fam["matched_features"])
        fam["members"].sort(key=lambda m: (m.get("priority_date") or "", m["jurisdiction"]))
        fam["representative"] = fam["members"][0]
        fam["jurisdictions"] = [m["jurisdiction"] for m in fam["members"]]
        out.append(fam)
    out.sort(key=lambda f: -f["best_score"])
    return out


def generate_search_concepts(db: Session, inn: Innovation) -> list[dict]:
    engine = TerminologyEngine(db)
    concepts = []
    for f in inn.features:
        if f.feature_type not in MATCHABLE:
            continue
        base = " ".join(x for x in (f.name, f.normalized_term or "", f.description or "") if x)
        matches = engine.normalize(base)
        concepts.append(
            {
                "feature_id": f.id,
                "feature_type": f.feature_type.value,
                "feature": f.name,
                "keywords": content_terms(base)[:10],
                "synonyms": engine.expand(matches),
            }
        )
    return concepts


def search_patents(db: Session, query: str, *, expansions: Optional[list[str]] = None, jurisdictions: Optional[list[str]] = None,
                   date_from: Optional[str] = None, date_to: Optional[str] = None, top_k: int = 10, workspace_id: Optional[str] = None) -> dict:
    f = RetrievalFilters(document_types=["PATENT"], workspace_id=workspace_id, date_from=date_from, date_to=date_to)
    r = retrieve(db, query, expansions=expansions, filters=f, intent="PRIOR_ART_SEARCH", top_k=top_k, per_document=1)
    pats = _patent_by_doc(db, [x["document_id"] for x in r.results])
    cards = []
    for x in r.results:
        p = pats.get(x["document_id"])
        if not p or (jurisdictions and p.jurisdiction not in jurisdictions):
            continue
        cards.append(patent_card(p, {
            "similarity_score": x["relevance"],
            "similarity_type": "+".join(x["methods"]),
            "relevant_passage": x["content"],
            "matched_section": x["section"],
            "why_retrieved": x["why_retrieved"],
            "matched_features": [],
        }))
    return {"results": cards, "families": group_by_family(cards), "trace": r.trace}


def match_innovation(db: Session, inn: Innovation, workspace_id: str) -> list[PatentFeatureMatch]:
    db.execute(delete(PatentFeatureMatch).where(PatentFeatureMatch.innovation_id == inn.id))
    engine = TerminologyEngine(db)
    created: list[PatentFeatureMatch] = []
    for f in inn.features:
        if f.feature_type not in MATCHABLE:
            continue
        q = " ".join(x for x in (f.name, f.description or "") if x)
        expansions = engine.expand(engine.normalize(" ".join([q, f.normalized_term or ""])))
        if f.normalized_term and f.normalized_term not in expansions:
            expansions.append(f.normalized_term)
        r = retrieve(
            db, q, expansions=expansions, filters=RetrievalFilters(document_types=["PATENT"], workspace_id=workspace_id),
            intent="PRIOR_ART_SEARCH", feature_terms=[f.name], top_k=4, per_document=1,
        )
        pats = _patent_by_doc(db, [x["document_id"] for x in r.results])
        for x in r.results:
            p = pats.get(x["document_id"])
            if not p or x["relevance"] < MIN_MATCH:
                continue
            body_terms = set(content_terms(x["content"] + " " + p.title))
            matched_terms = [t for t in content_terms(q + " " + " ".join(expansions)) if t in body_terms][:12]
            m = PatentFeatureMatch(
                innovation_id=inn.id,
                innovation_feature_id=f.id,
                patent_id=p.id,
                chunk_id=x["chunk_id"],
                match_type=MATCHABLE[f.feature_type],
                similarity_score=x["relevance"],
                matched_passage=x["content"][:1200],
                matched_terms=matched_terms,
                review_required=True,
            )
            db.add(m)
            created.append(m)
    db.flush()
    return created


def feature_matrix(db: Session, inn: Innovation) -> dict:
    rows = db.execute(
        select(PatentFeatureMatch).where(PatentFeatureMatch.innovation_id == inn.id).order_by(PatentFeatureMatch.similarity_score.desc())
    ).scalars().all()
    matrix, cards = [], {}
    for m in rows:
        p = m.patent
        matrix.append(
            {
                "match_id": m.id,
                "feature_id": m.innovation_feature_id,
                "feature": m.feature.name,
                "feature_type": m.feature.feature_type.value,
                "match_type": m.match_type,
                "patent_id": p.id,
                "document": p.title,
                "publication_number": p.publication_number,
                "family_id": p.patent_family_id,
                "passage": m.matched_passage,
                "matched_terms": m.matched_terms,
                "date": p.priority_date,
                "jurisdiction": p.jurisdiction,
                "similarity": round(m.similarity_score, 3),
                "review_required": m.review_required,
                "review_status": m.review_status,
                "is_demo": p.document.is_demo,
            }
        )
        c = cards.setdefault(p.id, patent_card(p, {"similarity_score": 0.0, "matched_features": [], "relevant_passage": m.matched_passage, "similarity_type": m.match_type}))
        c["similarity_score"] = max(c["similarity_score"], round(m.similarity_score, 3))
        if m.feature.name not in c["matched_features"]:
            c["matched_features"].append(m.feature.name)
    card_list = sorted(cards.values(), key=lambda c: -c["similarity_score"])
    return {"matrix": matrix, "patents": card_list, "families": group_by_family(card_list), "review_note": REVIEW_NOTE}
