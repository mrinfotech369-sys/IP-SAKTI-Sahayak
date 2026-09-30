"""Audit trail writer. Never pass confidential innovation text in metadata."""
import logging
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.security import safe_client_id
from app.models.orm import AuditLog

logger = logging.getLogger("ipsakti.audit")


def audit(
    db: Session,
    action: str,
    *,
    user_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    request: Optional[Request] = None,
    commit: bool = True,
    **metadata: Any,
) -> None:
    entry = AuditLog(
        action=action,
        user_id=user_id,
        workspace_id=workspace_id,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_=metadata,
        ip_hash=safe_client_id(request.client.host if request and request.client else None),
        request_id=getattr(request.state, "request_id", None) if request else None,
    )
    db.add(entry)
    if commit:
        db.commit()
    logger.info("audit action=%s entity=%s:%s user=%s", action, entity_type, entity_id, user_id)
