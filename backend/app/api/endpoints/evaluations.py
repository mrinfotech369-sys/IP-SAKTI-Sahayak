from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceCtx, get_db, workspace_ctx
from app.core.responses import AppError, ok
from app.models.orm import EvaluationQuestion, EvaluationRun, UserRole
from app.services.audit import audit
from app.services.evaluation import run_evaluation

router = APIRouter(prefix="/evaluations", tags=["RAG Evaluation"])


def run_view(r: EvaluationRun) -> dict:
    return {"id": r.id, "metrics": r.metrics, "results": r.results, "llm_provider": r.llm_provider,
            "embedding_provider": r.embedding_provider, "created_at": r.created_at.isoformat()}


@router.get("", summary="Latest evaluation run and question set")
def latest(ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    run = db.execute(select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(1)).scalar_one_or_none()
    history = db.execute(select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(10)).scalars().all()
    qs = db.execute(select(EvaluationQuestion).order_by(EvaluationQuestion.key)).scalars().all()
    return ok({
        "latest": run_view(run) if run else None,
        "history": [{"id": h.id, "created_at": h.created_at.isoformat(), "metrics": h.metrics} for h in history],
        "questions": [{"key": q.key, "category": q.category, "question": q.question, "language": q.language, "jurisdiction": q.jurisdiction,
                       "expected_abstention": q.expected_abstention} for q in qs],
    })


@router.post("/run", summary="Run the evaluation suite against the live pipeline (admin)")
def run(request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    if ctx.user.role != UserRole.ADMIN:
        raise AppError(403, "FORBIDDEN", "Only administrators can run the evaluation suite.")
    r = run_evaluation(db, ctx.workspace_id)
    audit(db, "evaluation_run", user_id=ctx.user.id, workspace_id=ctx.workspace_id, entity_type="evaluation", entity_id=r.id, request=request,
          passed=r.metrics.get("passed"), questions=r.metrics.get("questions"))
    return ok(run_view(r))
