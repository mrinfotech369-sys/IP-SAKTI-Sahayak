"""Evidence discovery for an innovation (regulatory, IP, TK/ABS, scientific)
and scientific evidence cards that separate ingredient vs formulation evidence."""
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.orm import Evidence, Innovation, ScientificStudy
from app.services.retrieval import RetrievalFilters, retrieve
from app.services.terminology import TerminologyEngine

TK_NO_EVIDENCE = (
    "No accessible evidence was found in the configured public and authorized sources. "
    "This does NOT establish that no traditional knowledge exists."
)


def _ingredient_names(inn: Innovation) -> list[str]:
    p = inn.profile
    if not p:
        return []
    names = []
    for i in p.ingredients or []:
        for k in ("name", "botanical_name", "normalized"):
            if i.get(k) and i[k] not in names:
                names.append(i[k])
    return names


def _upsert(db: Session, inn: Innovation, r: dict, etype: str, applicability: str, pending: dict, added_by: str = "SYSTEM") -> None:
    key = (r["chunk_id"], etype)
    existing = pending.get(key) or db.execute(
        select(Evidence).where(Evidence.innovation_id == inn.id, Evidence.chunk_id == r["chunk_id"], Evidence.evidence_type == etype)
    ).scalar_one_or_none()
    if existing:
        existing.relevance = max(existing.relevance, r["relevance"])
        return
    pending[key] = Evidence(
            innovation_id=inn.id,
            document_id=r["document_id"],
            chunk_id=r["chunk_id"],
            evidence_type=etype,
            relevance=r["relevance"],
            applicability=applicability,
            authority_tier=r["tier"],
            confidence=round(min(1.0, r["rerank_score"] * 1.3), 3),
            why_retrieved=r["why_retrieved"],
            added_by=added_by,
        )
    db.add(pending[key])


def discover(db: Session, inn: Innovation, workspace_id: str) -> dict:
    """Run category searches and persist system evidence. User-added evidence is kept."""
    db.execute(delete(Evidence).where(Evidence.innovation_id == inn.id, Evidence.added_by == "SYSTEM"))
    p = inn.profile
    engine = TerminologyEngine(db)
    ingredients = _ingredient_names(inn)
    expansions = engine.expand(engine.normalize(" ".join(ingredients)))
    form = (p.dosage_form if p else "") or ""
    use = (p.intended_use if p else "") or ""
    process = " ".join(x for x in ((p.extraction_method if p else None), (p.process if p else None)) if x)
    counts = {}
    traces = {}
    pending: dict = {}

    plans = []
    for j in inn.target_markets or []:
        plans.append(("REGULATORY", f"regulatory category licensing requirements claims labelling for oral herbal {form} {use}",
                      RetrievalFilters(jurisdictions=[j], domains=["REGULATORY"], workspace_id=workspace_id), "REGULATORY", "DIRECT", 6))
    plans.append(("IP", f"patentability traditional knowledge herbal invention {process} {' '.join(ingredients)}",
                  RetrievalFilters(domains=["IP"], document_types=["LEGISLATION", "TREATY"], workspace_id=workspace_id), "PATENT_SEARCH", "CONTEXTUAL", 5))
    plans.append(("TK", f"traditional knowledge biological resource access benefit sharing approval {' '.join(ingredients)}",
                  RetrievalFilters(domains=["TK_ABS"], workspace_id=workspace_id), "TRADITIONAL_KNOWLEDGE", "CONTEXTUAL", 6))
    for name in ingredients[:6]:
        plans.append(("SCIENTIFIC", f"{name} clinical study results",
                      RetrievalFilters(domains=["SCIENTIFIC"], workspace_id=workspace_id), "SCIENTIFIC_EVIDENCE", "INGREDIENT_ONLY", 3))

    for etype, q, f, intent, applicability, k in plans:
        r = retrieve(db, q, expansions=expansions, filters=f, intent=intent, top_k=k)
        counts[etype] = counts.get(etype, 0) + len(r.results)
        traces.setdefault(etype, []).append({"query": q, "selected": len(r.results), "counts": r.trace["counts"]})
        for x in r.results:
            _upsert(db, inn, x, etype, applicability, pending)
    db.flush()
    return {"counts": counts, "traces": traces}


def evidence_list(db: Session, inn: Innovation, etype: str | None = None) -> list[dict]:
    q = select(Evidence).where(Evidence.innovation_id == inn.id)
    if etype:
        q = q.where(Evidence.evidence_type == etype)
    out = []
    for e in db.execute(q.order_by(Evidence.relevance.desc())).scalars().all():
        d, c = e.document, e.chunk
        out.append(
            {
                "id": e.id,
                "evidence_type": e.evidence_type,
                "applicability": e.applicability,
                "relevance": round(e.relevance, 3),
                "confidence": e.confidence,
                "authority_tier": e.authority_tier,
                "why_retrieved": e.why_retrieved,
                "added_by": e.added_by,
                "notes": e.notes,
                "document_id": d.id,
                "chunk_id": c.id,
                "title": d.title,
                "authority": d.source.authority,
                "jurisdiction": d.jurisdiction,
                "document_type": d.document_type,
                "section": c.section,
                "passage": c.content,
                "url": d.url,
                "publication_date": d.publication_date,
                "effective_date": d.effective_date,
                "last_checked": d.last_checked.isoformat() if d.last_checked else None,
                "is_demo": d.is_demo,
                "review_status": d.review_status,
                "superseded": bool(d.superseded_by_document_id),
            }
        )
    return out


def scientific_cards(db: Session, inn: Innovation) -> dict:
    ingredients = _ingredient_names(inn)
    engine = TerminologyEngine(db)
    names = {n.lower() for n in engine.expand(engine.normalize(" ".join(ingredients)))} | {n.lower() for n in ingredients}
    studies = db.execute(select(ScientificStudy)).scalars().all()
    cards, covered = [], set()
    n_ing = len({i.get("name") for i in (inn.profile.ingredients if inn.profile else [])})
    for s in studies:
        s_ings = {i.lower() for i in (s.ingredients or [])}
        hit = sorted(s_ings & names)
        if not hit and s.evidence_level != "SAFETY":
            continue
        for h in hit:
            covered.add(h)
        is_formulation = s.evidence_level == "FORMULATION"
        if s.evidence_level == "SAFETY":
            applicability = "Quality/safety context for Ayurvedic products generally; not specific to this innovation."
        elif is_formulation:
            applicability = "Formulation-level evidence — check that dose, extract and composition match this innovation."
        else:
            applicability = (
                f"Ingredient-level evidence ({', '.join(hit)}). It does NOT establish effects of this innovation's final "
                f"formulation, which combines {n_ing} ingredients with a different extract, dose and process."
            )
        cards.append(
            {
                "id": s.id,
                "document_id": s.document_id,
                "title": s.title,
                "authors": s.authors,
                "year": s.year,
                "journal": s.journal,
                "identifier": s.identifier,
                "study_type": s.study_type,
                "population": s.population,
                "intervention": s.intervention,
                "dosage": s.dosage,
                "duration": s.duration,
                "outcome": s.outcome,
                "limitations": s.limitations,
                "relevant_ingredients": hit,
                "evidence_level": s.evidence_level,
                "applicability": applicability,
                "source": s.document.source.name,
                "url": s.document.url or (f"https://pubmed.ncbi.nlm.nih.gov/{s.identifier.split(':')[-1].strip()}/" if s.identifier and "PMID" in s.identifier else None),
                "review_status": s.document.review_status,
                "tier": s.document.source.authority_tier,
            }
        )
    cards.sort(key=lambda c: (c["evidence_level"] != "FORMULATION", c["evidence_level"] == "SAFETY", -(c["year"] or 0)))
    uncovered = [i for i in ingredients if i.lower() not in covered]
    return {
        "cards": cards,
        "formulation_evidence_found": any(c["evidence_level"] == "FORMULATION" for c in cards),
        "ingredients_without_evidence": uncovered,
        "notice": "Ingredient evidence is kept separate from finished-formulation evidence and is never transferred automatically.",
    }


def tk_context(db: Session, inn: Innovation, workspace_id: str) -> dict:
    ingredients = _ingredient_names(inn)
    engine = TerminologyEngine(db)
    matches = engine.normalize(" ".join(ingredients))
    r = retrieve(
        db, f"traditional knowledge {' '.join(ingredients)} benefit sharing access patent disclosure",
        expansions=engine.expand(matches), filters=RetrievalFilters(domains=["TK_ABS", "IP"], workspace_id=workspace_id),
        intent="TRADITIONAL_KNOWLEDGE", top_k=8,
    )
    return {
        "terminology": [m.to_dict() for m in matches],
        "context": r.results,
        "tk_records_found": False,
        "tkdl_access": {"status": "RESTRICTED_NOT_QUERIED", "label": "TKDL access: restricted — not queried",
                        "meaning": "TKDL was not searched. 'No result' here is NOT a finding that no traditional knowledge exists."},
        "public_tk_sources_searched": sorted({x["source_name"] for x in r.results}),
        "tk_notice": TK_NO_EVIDENCE,
        "access_limitation": "TKDL records are restricted to authorised users under access agreements. This system has no TKDL access and does not scrape or reproduce restricted records.",
        "attribution": "Where an invention draws on traditional knowledge, disclose source and origin (Patents Act s.10(4)(ii)(D)) and consider benefit-sharing obligations (Biological Diversity Act s.6).",
        "possible_overlap": [
            f"'{m.canonical}' is a classical Ayurvedic ingredient ({m.sanskrit or m.canonical}); formulations using it may overlap with documented traditional knowledge."
            for m in matches if m.domain in ("BOTANICAL", "FORMULATION")
        ],
        "human_escalation": "Request a professional prior-art search (including TKDL via an authorised patent office route) before filing.",
        "trace": r.trace,
    }
