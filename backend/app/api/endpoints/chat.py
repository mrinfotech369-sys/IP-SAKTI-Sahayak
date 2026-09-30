import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceCtx, get_db, rate_limit, workspace_ctx
from app.core.responses import AppError, not_found, ok
from app.models.orm import Claim, ClaimEvidence, Conversation, Innovation, Message, RetrievalResult, Severity, SupportStatus
from app.schemas import ChatIn, MessageFeedback
from app.services.audit import audit
from app.services.research import run_research

router = APIRouter(tags=["Research Assistant"])
log = logging.getLogger("ipsakti.chat")

RISKY_TYPES = {"FACT": Severity.MEDIUM, "INFERENCE": Severity.HIGH, "USER_PROVIDED": Severity.LOW, "UNCERTAINTY": Severity.LOW}


def conv_view(c: Conversation) -> dict:
    return {"id": c.id, "title": c.title, "language": c.language, "mode": c.mode, "innovation_id": c.innovation_id,
            "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat()}


def msg_view(m: Message) -> dict:
    return {"id": m.id, "role": m.role, "content": m.content, "payload": m.payload, "feedback": m.feedback, "flagged": m.flagged,
            "created_at": m.created_at.isoformat()}


def _own_conversation(db: Session, ctx: WorkspaceCtx, conversation_id: str) -> Conversation:
    c = db.get(Conversation, conversation_id)
    if not c or c.workspace_id != ctx.workspace_id or c.user_id != ctx.user.id:
        raise not_found("Conversation")
    return c


def _persist(db: Session, conv: Conversation, msg: Message, result: dict) -> None:
    ev = {e["n"]: e for e in result.get("evidence", [])}
    for rank, e in enumerate(result.get("evidence", []), start=1):
        db.add(RetrievalResult(conversation_id=conv.id, message_id=msg.id, query=result["trace"]["retrieval"]["query"], document_id=e["document_id"],
                               chunk_id=e["chunk_id"], retrieval_method="+".join(e["methods"]), score=e["relevance"], rerank_score=e["rerank_score"], rank=rank))
    for kp in result.get("key_points", []):
        claim = Claim(conversation_id=conv.id, message_id=msg.id, innovation_id=conv.innovation_id, claim_text=kp["text"], claim_type=kp["type"],
                      risk_level=RISKY_TYPES.get(kp["type"], Severity.MEDIUM), support_status=SupportStatus(kp["status"]))
        db.add(claim)
        db.flush()
        for n in kp["citations"] or [None]:
            db.add(ClaimEvidence(claim_id=claim.id, chunk_id=ev[n]["chunk_id"] if n in ev else None, support_status=SupportStatus(kp["status"]),
                                 entailment_score=kp["score"], checks=kp["checks"], notes="; ".join(kp["notes"]) or None))


@router.post("/chat", summary="Ask the AI Research Assistant (full RAG + verification pipeline)",
             dependencies=[Depends(rate_limit("chat"))])
def chat(body: ChatIn, request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    inn = None
    if body.innovation_id:
        inn = db.get(Innovation, body.innovation_id)
        if not inn or inn.workspace_id != ctx.workspace_id:
            raise not_found("Innovation")
    if body.conversation_id:
        conv = _own_conversation(db, ctx, body.conversation_id)
        if inn is None and conv.innovation_id:
            inn = db.get(Innovation, conv.innovation_id)
    else:
        conv = Conversation(workspace_id=ctx.workspace_id, innovation_id=inn.id if inn else None, user_id=ctx.user.id,
                            title=body.message[:80], language=body.language or "en", mode=body.mode or "GENERAL")
        db.add(conv)
        db.flush()
    user_msg = Message(conversation_id=conv.id, role="user", content=body.message,
                       payload={"jurisdiction": body.jurisdiction, "mode": body.mode, "language": body.language, "filters": body.filters})
    db.add(user_msg)
    db.flush()
    audit(db, "search_started", user_id=ctx.user.id, workspace_id=ctx.workspace_id, entity_type="conversation", entity_id=conv.id,
          request=request, commit=False, mode=body.mode, jurisdiction=body.jurisdiction)
    try:
        result = run_research(db, body.message, workspace_id=ctx.workspace_id, language=body.language, jurisdiction=body.jurisdiction,
                              mode=body.mode, innovation=inn, filters=body.filters)
    except Exception as exc:
        db.rollback()
        log.exception("research pipeline failed")
        raise AppError(503, "RESEARCH_PIPELINE_FAILED",
                       "The research pipeline could not complete (retrieval or database error). Your question was not answered; please retry. "
                       "If this persists, check System Health.") from exc
    asst = Message(conversation_id=conv.id, role="assistant", content=result["answer"], payload=result)
    db.add(asst)
    db.flush()
    if "retrieval" in result.get("trace", {}):
        _persist(db, conv, asst, result)
    conv.language = result["language"]
    audit(db, "search_completed", user_id=ctx.user.id, workspace_id=ctx.workspace_id, entity_type="conversation", entity_id=conv.id,
          request=request, commit=False, type=result["type"], evidence_status=result["evidence_status"], retrieved=len(result.get("evidence", [])))
    db.commit()
    log.info("chat conversation=%s type=%s evidence=%d latency_ms=%s", conv.id, result["type"], len(result.get("evidence", [])), result["trace"].get("latency_ms"))
    return ok({"conversation": conv_view(conv), "user_message": msg_view(user_msg), "message": msg_view(asst)})


@router.get("/conversations")
def conversations(innovation_id: str | None = None, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    q = select(Conversation).where(Conversation.workspace_id == ctx.workspace_id, Conversation.user_id == ctx.user.id)
    if innovation_id:
        q = q.where(Conversation.innovation_id == innovation_id)
    return ok([conv_view(c) for c in db.execute(q.order_by(Conversation.updated_at.desc()).limit(100)).scalars()])


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: str, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    return ok(conv_view(_own_conversation(db, ctx, conversation_id)))


@router.get("/conversations/{conversation_id}/messages")
def messages(conversation_id: str, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    c = _own_conversation(db, ctx, conversation_id)
    rows = db.execute(select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at)).scalars()
    return ok([msg_view(m) for m in rows])


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    c = _own_conversation(db, ctx, conversation_id)
    db.delete(c)
    audit(db, "conversation_deleted", user_id=ctx.user.id, workspace_id=ctx.workspace_id, entity_type="conversation", entity_id=conversation_id, request=request)
    return ok({"deleted": True})


@router.patch("/messages/{message_id}")
def message_feedback(message_id: str, body: MessageFeedback, request: Request, ctx: WorkspaceCtx = Depends(workspace_ctx), db: Session = Depends(get_db)):
    m = db.get(Message, message_id)
    if not m:
        raise not_found("Message")
    _own_conversation(db, ctx, m.conversation_id)
    if body.feedback is not None:
        m.feedback = body.feedback
    if body.flagged is not None:
        m.flagged = body.flagged
    audit(db, "response_flagged" if body.flagged else "response_feedback", user_id=ctx.user.id, workspace_id=ctx.workspace_id,
          entity_type="message", entity_id=m.id, request=request, feedback=body.feedback)
    return ok(msg_view(m))
