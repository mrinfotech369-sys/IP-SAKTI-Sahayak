from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceCtx, get_db, rate_limit, workspace_ctx
from app.core.responses import AppError, not_found, ok
from app.models.orm import Innovation, ScientificStudy, WorkspaceRole
from app.schemas import ClassificationIn, SearchIn, VerifyIn
from app.services import patents as patent_svc
from app.services import regulatory as reg_svc
from app.services.audit import audit
from app.services.query_understanding import analyze_query
from app.services.retrieval import RetrievalFilters, retrieve
from app.services.terminology import TerminologyEngine
from app.services.verification import load_chunk, verify_claim

router = APIRouter(tags=["Search & Verification"])


def _filters(body: SearchIn, ctx: WorkspaceCtx, **override) -> RetrievalFilters:
    f = RetrievalFilters(
        jurisdictions=list(body.jurisdictions), domains=list(body.domains), document_types=list(body.document_types), max_tier=body.max_tier,
        language=body.language, include_superseded=body.include_superseded, workspace_id=ctx.workspace_id,
        date_from=body.date_from, date_to=body.date_to,
    )
    for k, v in override.items():
        setattr(f, k, v)
    return f


def _expand(db: Session, q: str) -> tuple[list[dict], list[str]]:
    eng = TerminologyEngine(db)
    m = eng.normalize(q)
    return [x.to_dict() for x in m], eng.expand(m)


def _audit_search(db, ctx, request, kind, body, n):
    audit(db, "search_completed", user_id=ctx.user.id, workspace_id=ctx.workspace_id, entity_type="search", request=request, kind=kind, results=n,
          jurisdictions=body.jurisdictions)


@router.post("/search", dependencies=[Depends(rate_limit("search"))], summary="Hybrid search over all configured sources")
def search(body: SearchIn, request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    a = analyze_query(body.query)
    terms, exp = _expand(db, body.query)
    r = retrieve(db, body.query, expansions=exp, filters=_filters(body, ctx), intent=a.intent, top_k=body.top_k)
    _audit_search(db, ctx, request, "general", body, len(r.results))
    return ok({"results": r.results, "terminology": terms, "analysis": a.to_dict(), "trace": r.trace})


@router.post("/search/patents", dependencies=[Depends(rate_limit("search"))])
def search_patents(body: SearchIn, request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    terms, exp = _expand(db, body.query)
    res = patent_svc.search_patents(db, body.query, expansions=exp, jurisdictions=list(body.jurisdictions) or None, date_from=body.date_from,
                                    date_to=body.date_to, top_k=body.top_k, workspace_id=ctx.workspace_id)
    _audit_search(db, ctx, request, "patents", body, len(res["results"]))
    return ok({**res, "terminology": terms, "review_note": patent_svc.REVIEW_NOTE})


@router.post("/search/scientific", dependencies=[Depends(rate_limit("search"))])
def search_scientific(body: SearchIn, request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    terms, exp = _expand(db, body.query)
    r = retrieve(db, body.query, expansions=exp, filters=_filters(body, ctx, domains=["SCIENTIFIC"], jurisdictions=[]), intent="SCIENTIFIC_EVIDENCE",
                 top_k=body.top_k, per_document=1)
    doc_ids = [x["document_id"] for x in r.results]
    studies = {s.document_id: s for s in db.execute(select(ScientificStudy).where(ScientificStudy.document_id.in_(doc_ids))).scalars()} if doc_ids else {}
    cards = []
    for x in r.results:
        s = studies.get(x["document_id"])
        cards.append({**x, "study": {
            "title": s.title, "authors": s.authors, "year": s.year, "journal": s.journal, "study_type": s.study_type, "population": s.population,
            "intervention": s.intervention, "dosage": s.dosage, "duration": s.duration, "outcome": s.outcome, "limitations": s.limitations,
            "evidence_level": s.evidence_level, "identifier": s.identifier, "ingredients": s.ingredients,
        } if s else None})
    _audit_search(db, ctx, request, "scientific", body, len(cards))
    return ok({"results": cards, "terminology": terms, "trace": r.trace,
               "notice": "Ingredient-level evidence does not establish effects of a finished formulation."})


@router.post("/search/regulatory", dependencies=[Depends(rate_limit("search"))])
def search_regulatory(body: SearchIn, request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    if not body.jurisdictions:
        raise AppError(422, "JURISDICTION_REQUIRED", "Which market are you evaluating? Select India, USA and/or Australia.")
    terms, exp = _expand(db, body.query)
    by_j = {}
    for j in body.jurisdictions:
        r = retrieve(db, body.query, expansions=exp, filters=_filters(body, ctx, jurisdictions=[j], domains=body.domains or ["REGULATORY"]),
                     intent="REGULATORY", top_k=body.top_k)
        by_j[j] = {"results": r.results, "trace": r.trace}
    _audit_search(db, ctx, request, "regulatory", body, sum(len(v["results"]) for v in by_j.values()))
    return ok({"by_jurisdiction": by_j, "terminology": terms})


@router.post("/citations/verify", summary="Verify whether a passage supports a claim")
def verify(body: VerifyIn, request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    chunk = load_chunk(db, body.chunk_id) if body.chunk_id else None
    if body.chunk_id and not chunk:
        res = {"status": "UNSUPPORTED", "score": 0.0, "checks": {"source_exists": False}, "notes": ["Cited passage does not exist."]}
    else:
        res = verify_claim(body.claim, chunk, jurisdictions=list(body.jurisdictions) or None)
    audit(db, "citation_verified", user_id=ctx.user.id, workspace_id=ctx.workspace_id, entity_type="chunk", entity_id=body.chunk_id, request=request, status=res["status"])
    return ok({**res, "passage": chunk})


@router.get("/classification/questions")
def classification_questions(ctx: WorkspaceCtx = Depends(workspace_ctx)):
    return ok(reg_svc.QUESTIONS)


@router.post("/classification/analyze", summary="Provisional product classification")
def classification(body: ClassificationIn, request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    if body.innovation_id:
        inn = db.get(Innovation, body.innovation_id)
        if not inn or inn.workspace_id != ctx.workspace_id:
            raise not_found("Innovation")
        ctx.require(WorkspaceRole.RESEARCHER)
    res = reg_svc.classify(db, body.answers, ctx.workspace_id)
    audit(db, "classification_analyzed", user_id=ctx.user.id, workspace_id=ctx.workspace_id, entity_type="innovation", entity_id=body.innovation_id, request=request)
    return ok(res)


@router.get("/regulatory/{jurisdiction}", summary="Regulatory pathways for a jurisdiction (IN, US, AU)")
def regulatory(jurisdiction: str, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    j = jurisdiction.upper()
    if j not in ("IN", "US", "AU"):
        raise AppError(404, "UNKNOWN_JURISDICTION", "Supported jurisdictions are IN, US and AU.")
    return ok(reg_svc.jurisdiction_overview(db, j))
