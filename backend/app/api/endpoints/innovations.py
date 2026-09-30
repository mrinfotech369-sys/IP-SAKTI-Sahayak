from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceCtx, get_db, innovation_ctx, workspace_ctx
from app.core.responses import AppError, not_found, ok
from app.models.orm import (
    Confidentiality,
    Escalation,
    Evidence,
    EvidenceGap,
    Innovation,
    InnovationStatus,
    PatentFeatureMatch,
    Workspace,
    WorkspaceRole,
)
from app.schemas import (
    ClassificationIn,
    EvidenceAddIn,
    GapPatch,
    InnovationCreate,
    InnovationPatch,
    MatchPatch,
    ProfilePatch,
)
from app.services import analysis as analysis_svc
from app.services import evidence as evidence_svc
from app.services import patents as patent_svc
from app.services import regulatory as reg_svc
from app.services.audit import audit
from app.services.profile import apply_profile_edits, build_profile
from app.services.verification import load_chunk

router = APIRouter(prefix="/innovations", tags=["Innovations"])

CONFIDENTIAL_WARNING = (
    "This innovation is marked confidential. Do not disclose unnecessary unpublished invention details. "
    "This system does not create attorney-client privilege."
)


def profile_view(inn: Innovation) -> dict | None:
    p = inn.profile
    if not p:
        return None
    return {
        "ingredients": p.ingredients, "botanical_names": p.botanical_names, "chemical_entities": p.chemical_entities,
        "composition": p.composition, "process": p.process, "extraction_method": p.extraction_method,
        "dosage_form": p.dosage_form, "route": p.route, "intended_use": p.intended_use, "claims": p.claims,
        "target_market": p.target_market, "manufacturing_location": p.manufacturing_location,
        "structured_features": p.structured_features, "search_terms": p.search_terms, "terminology": p.terminology,
        "assumptions": p.assumptions, "missing_information": p.missing_information, "ambiguities": p.ambiguities,
        "extraction_method_used": p.extraction_method_used, "user_confirmed": p.user_confirmed,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def card(db: Session, inn: Innovation) -> dict:
    counts = {
        "evidence": db.scalar(select(func.count()).select_from(Evidence).where(Evidence.innovation_id == inn.id)),
        "patent_matches": db.scalar(select(func.count(func.distinct(PatentFeatureMatch.patent_id))).where(PatentFeatureMatch.innovation_id == inn.id)),
        "evidence_gaps": db.scalar(select(func.count()).select_from(EvidenceGap).where(EvidenceGap.innovation_id == inn.id, EvidenceGap.status == "OPEN")),
        "open_escalations": db.scalar(select(func.count()).select_from(Escalation).where(Escalation.innovation_id == inn.id, Escalation.status.in_(["OPEN", "IN_REVIEW"]))),
    }
    return {
        "id": inn.id, "name": inn.name, "description": inn.description, "status": inn.status.value,
        "confidentiality_level": inn.confidentiality_level.value, "jurisdictions": inn.target_markets or [],
        "is_demo": inn.is_demo, "updated_at": inn.updated_at.isoformat(), "created_at": inn.created_at.isoformat(),
        "counts": counts, "completion": analysis_svc.completion(db, inn),
    }


def detail(db: Session, inn: Innovation) -> dict:
    return {
        **card(db, inn),
        "innovation_type": inn.innovation_type,
        "wizard_input": inn.wizard_input,
        "profile": profile_view(inn),
        "features": [
            {"id": f.id, "feature_type": f.feature_type.value, "name": f.name, "description": f.description,
             "normalized_term": f.normalized_term, "importance": f.importance, "source": f.source}
            for f in inn.features
        ],
        "analysis": {k: v for k, v in (inn.analysis or {}).items() if k in ("last_run_at", "last_run_steps", "last_run_ms")},
        "confidential_warning": CONFIDENTIAL_WARNING if inn.confidentiality_level == Confidentiality.CONFIDENTIAL else None,
    }


@router.get("", summary="List innovations in the current workspace")
def list_innovations(ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    rows = db.execute(select(Innovation).where(Innovation.workspace_id == ctx.workspace_id).order_by(Innovation.updated_at.desc())).scalars().all()
    return ok([card(db, i) for i in rows], workspace_id=ctx.workspace_id)


@router.post("", summary="Create an innovation from the profiler wizard")
def create_innovation(body: InnovationCreate, request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    ctx.require(WorkspaceRole.RESEARCHER)
    w = body.wizard
    name = (w.basic.get("name") or "").strip()
    if len(name) < 2:
        raise AppError(422, "VALIDATION_ERROR", "Innovation name is required (Step 1 — Basic Information).")
    if w.confidentiality == "CONFIDENTIAL" and not body.acknowledge_confidentiality:
        raise AppError(428, "CONFIDENTIALITY_ACK_REQUIRED", CONFIDENTIAL_WARNING)
    inn = Innovation(
        workspace_id=ctx.workspace_id, name=name[:300], description=w.basic.get("description", ""), innovation_type=w.basic.get("innovation_type"),
        confidentiality_level=Confidentiality(w.confidentiality), target_markets=list(w.markets), wizard_input=w.model_dump(),
        created_by=ctx.user.id, analysis={},
    )
    db.add(inn)
    db.flush()
    audit(db, "innovation_created", user_id=ctx.user.id, workspace_id=ctx.workspace_id, entity_type="innovation", entity_id=inn.id, request=request, commit=False,
          confidentiality=w.confidentiality)
    if body.generate_profile:
        build_profile(db, inn, w.model_dump())
        audit(db, "profile_generated", user_id=ctx.user.id, workspace_id=ctx.workspace_id, entity_type="innovation", entity_id=inn.id, request=request, commit=False)
        if body.run_analysis:
            analysis_svc.run_analysis(db, inn, ctx.workspace_id)
            audit(db, "search_completed", user_id=ctx.user.id, workspace_id=ctx.workspace_id, entity_type="innovation", entity_id=inn.id, request=request, commit=False, scope="full_analysis")
    db.commit()
    return ok(detail(db, inn))


@router.get("/{innovation_id}")
def get_innovation(ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    _, inn = ic
    return ok(detail(db, inn))


@router.patch("/{innovation_id}")
def update_innovation(body: InnovationPatch, request: Request, ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    ctx, inn = ic
    ctx.require(WorkspaceRole.RESEARCHER)
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        if k == "status":
            v = InnovationStatus(v)
        elif k == "confidentiality_level":
            v = Confidentiality(v)
        setattr(inn, k, v)
    audit(db, "innovation_updated", user_id=ctx.user.id, workspace_id=inn.workspace_id, entity_type="innovation", entity_id=inn.id, request=request,
          fields=sorted(changes))
    return ok(detail(db, inn))


@router.delete("/{innovation_id}")
def delete_innovation(request: Request, ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    ctx, inn = ic
    ctx.require(WorkspaceRole.ADMIN)
    audit(db, "innovation_deleted", user_id=ctx.user.id, workspace_id=inn.workspace_id, entity_type="innovation", entity_id=inn.id, request=request, commit=False, name=inn.name)
    db.delete(inn)
    db.commit()
    return ok({"deleted": True})


@router.post("/{innovation_id}/profile/generate", summary="(Re)generate the structured profile from wizard input")
def generate_profile(request: Request, ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    ctx, inn = ic
    ctx.require(WorkspaceRole.RESEARCHER)
    prof = build_profile(db, inn, inn.wizard_input or {})
    audit(db, "profile_generated", user_id=ctx.user.id, workspace_id=inn.workspace_id, entity_type="innovation", entity_id=inn.id, request=request,
          method=prof.extraction_method_used)
    return ok(detail(db, inn))


@router.patch("/{innovation_id}/profile", summary="Edit/confirm the extracted profile")
def edit_profile(body: ProfilePatch, request: Request, ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    ctx, inn = ic
    ctx.require(WorkspaceRole.RESEARCHER)
    if not inn.profile:
        raise AppError(409, "NO_PROFILE", "Generate the profile first.")
    apply_profile_edits(db, inn, body.model_dump(exclude_none=True))
    audit(db, "innovation_updated", user_id=ctx.user.id, workspace_id=inn.workspace_id, entity_type="innovation", entity_id=inn.id, request=request, scope="profile")
    return ok(detail(db, inn))


@router.post("/{innovation_id}/analyze", summary="Run evidence discovery, patent matching, classification and gap detection")
def analyze(request: Request, ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    ctx, inn = ic
    ctx.require(WorkspaceRole.RESEARCHER)
    if not inn.profile:
        raise AppError(409, "NO_PROFILE", "Generate the innovation profile before running analysis.")
    audit(db, "search_started", user_id=ctx.user.id, workspace_id=inn.workspace_id, entity_type="innovation", entity_id=inn.id, request=request, commit=False)
    res = analysis_svc.run_analysis(db, inn, inn.workspace_id)
    audit(db, "search_completed", user_id=ctx.user.id, workspace_id=inn.workspace_id, entity_type="innovation", entity_id=inn.id, request=request, commit=False, steps=res["steps"])
    db.commit()
    return ok({**res, "innovation": card(db, inn)})


# --------------------------------------------------------------------- evidence
@router.get("/{innovation_id}/evidence")
def get_evidence(evidence_type: str | None = None, ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    _, inn = ic
    return ok(evidence_svc.evidence_list(db, inn, evidence_type))


@router.post("/{innovation_id}/evidence", summary="Add a retrieved passage to the innovation's evidence")
def add_evidence(body: EvidenceAddIn, request: Request, ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    ctx, inn = ic
    ctx.require(WorkspaceRole.RESEARCHER)
    chunk = load_chunk(db, body.chunk_id)
    if not chunk:
        raise not_found("Passage")
    exists = db.execute(select(Evidence).where(Evidence.innovation_id == inn.id, Evidence.chunk_id == body.chunk_id, Evidence.evidence_type == body.evidence_type)).scalar_one_or_none()
    if exists:
        exists.added_by = "USER"  # user confirmed a system-found passage; survives re-analysis
        if body.notes:
            exists.notes = body.notes
    else:
        db.add(Evidence(innovation_id=inn.id, document_id=chunk["document_id"], chunk_id=body.chunk_id, evidence_type=body.evidence_type,
                        relevance=1.0, applicability="USER_SELECTED", authority_tier=int(chunk["tier"]), confidence=0.0,
                        why_retrieved="Added by user from research results", notes=body.notes, added_by="USER"))
    audit(db, "evidence_added", user_id=ctx.user.id, workspace_id=inn.workspace_id, entity_type="innovation", entity_id=inn.id, request=request, chunk_id=body.chunk_id)
    return ok({"added": not exists})


@router.get("/{innovation_id}/scientific")
def scientific(ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    _, inn = ic
    return ok(evidence_svc.scientific_cards(db, inn))


@router.get("/{innovation_id}/tk")
def traditional_knowledge(ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    ctx, inn = ic
    return ok(evidence_svc.tk_context(db, inn, inn.workspace_id))


# --------------------------------------------------------------------- patents
@router.get("/{innovation_id}/patents")
def patents(ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    _, inn = ic
    return ok({**patent_svc.feature_matrix(db, inn), "search_concepts": patent_svc.generate_search_concepts(db, inn)})


@router.patch("/{innovation_id}/patents/matches/{match_id}")
def review_match(match_id: str, body: MatchPatch, request: Request, ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    ctx, inn = ic
    ctx.require(WorkspaceRole.REVIEWER)
    m = db.get(PatentFeatureMatch, match_id)
    if not m or m.innovation_id != inn.id:
        raise not_found("Patent match")
    m.review_status = body.review_status
    audit(db, "patent_match_reviewed", user_id=ctx.user.id, workspace_id=inn.workspace_id, entity_type="innovation", entity_id=inn.id, request=request,
          match_id=match_id, review_status=body.review_status)
    return ok({"id": m.id, "review_status": m.review_status})


# --------------------------------------------------------------------- gaps, risk, graph
@router.get("/{innovation_id}/evidence-gaps")
def gaps(ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    _, inn = ic
    rows = db.execute(select(EvidenceGap).where(EvidenceGap.innovation_id == inn.id)).scalars().all()
    rows.sort(key=lambda g: (-analysis_svc.SEV_RANK[g.severity.value], g.category))
    return ok([analysis_svc.gap_view(g) for g in rows])


@router.patch("/{innovation_id}/evidence-gaps/{gap_id}")
def update_gap(gap_id: str, body: GapPatch, request: Request, ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    ctx, inn = ic
    ctx.require(WorkspaceRole.RESEARCHER)
    g = db.get(EvidenceGap, gap_id)
    if not g or g.innovation_id != inn.id:
        raise not_found("Evidence gap")
    g.status = body.status
    audit(db, "gap_status_changed", user_id=ctx.user.id, workspace_id=inn.workspace_id, entity_type="innovation", entity_id=inn.id, request=request, gap=g.gap_key, status=body.status)
    return ok(analysis_svc.gap_view(g))


@router.get("/{innovation_id}/risk-map")
def risk(ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    _, inn = ic
    return ok(analysis_svc.risk_map(db, inn))


@router.get("/{innovation_id}/graph")
def graph(ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    _, inn = ic
    return ok(analysis_svc.evidence_graph(db, inn))


# --------------------------------------------------------------------- classification & regulatory
@router.get("/{innovation_id}/classification")
def get_classification(ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    _, inn = ic
    state = inn.analysis or {}
    return ok({
        "questions": reg_svc.QUESTIONS,
        "answers": state.get("classification_answers") or reg_svc.defaults_from_profile(inn),
        "result": state.get("classification"),
    })


@router.post("/{innovation_id}/classification")
def run_classification(body: ClassificationIn, request: Request, ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    ctx, inn = ic
    ctx.require(WorkspaceRole.RESEARCHER)
    res = reg_svc.classify(db, body.answers, inn.workspace_id)
    state = dict(inn.analysis or {})
    state["classification_answers"] = body.answers
    if res["status"] == "OK":
        state["classification"] = res
    inn.analysis = state
    db.flush()
    analysis_svc.detect_gaps(db, inn)
    audit(db, "classification_analyzed", user_id=ctx.user.id, workspace_id=inn.workspace_id, entity_type="innovation", entity_id=inn.id, request=request,
          markets=body.answers.get("markets"))
    return ok(res)


@router.get("/{innovation_id}/regulatory")
def regulatory_passport(ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    _, inn = ic
    pp = reg_svc.passport(db, inn, inn.workspace_id)
    return ok({**pp, "comparison": reg_svc.comparison(pp["passport"])})


@router.get("/{innovation_id}/workspace", include_in_schema=False)
def innovation_workspace(ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    _, inn = ic
    w = db.get(Workspace, inn.workspace_id)
    return ok({"id": w.id, "name": w.name, "confidential_mode": w.confidential_mode})


@router.get("/{innovation_id}/summary", summary="Structured analysis: classification → pathway → IP considerations → evidence → next steps")
def innovation_summary(ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    _, inn = ic
    return ok(analysis_svc.summary(db, inn))


@router.get("/{innovation_id}/provisions", summary="Provision-level relevance flags (not legal determinations)")
def innovation_provisions(ic=Depends(innovation_ctx), db: Session = Depends(get_db)):
    from app.services.governance import provision_map
    _, inn = ic
    return ok(provision_map(db, inn))
