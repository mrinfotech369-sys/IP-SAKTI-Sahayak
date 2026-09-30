"""Relational domain model for IP-SAKTI Sahayak (Postgres + pgvector)."""
import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enum(e: type[enum.Enum], name: str) -> Enum:
    return Enum(e, name=name, native_enum=False, length=40)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"


class WorkspaceRole(str, enum.Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    RESEARCHER = "RESEARCHER"
    REVIEWER = "REVIEWER"
    VIEWER = "VIEWER"


class Confidentiality(str, enum.Enum):
    PUBLIC_RESEARCH = "PUBLIC_RESEARCH"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"


class InnovationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PROFILED = "PROFILED"
    IN_RESEARCH = "IN_RESEARCH"
    IN_REVIEW = "IN_REVIEW"
    COMPLETED = "COMPLETED"


class FeatureType(str, enum.Enum):
    INGREDIENT = "INGREDIENT"
    COMPOSITION = "COMPOSITION"
    PROCESS = "PROCESS"
    EXTRACTION = "EXTRACTION"
    DELIVERY = "DELIVERY"
    DOSAGE_FORM = "DOSAGE_FORM"
    CLAIM = "CLAIM"
    USE = "USE"
    MANUFACTURING = "MANUFACTURING"
    OTHER = "OTHER"


class RetrievalMethod(str, enum.Enum):
    BM25 = "BM25"
    DENSE = "DENSE"
    GRAPH = "GRAPH"
    METADATA = "METADATA"
    PATENT = "PATENT"
    HYBRID = "HYBRID"


class SupportStatus(str, enum.Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    CONFLICTING = "CONFLICTING"
    INSUFFICIENT = "INSUFFICIENT"


class Severity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EscalationStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class EscalationType(str, enum.Enum):
    IP_REVIEW = "IP_REVIEW"
    REGULATORY_REVIEW = "REGULATORY_REVIEW"
    DOMAIN_REVIEW = "DOMAIN_REVIEW"
    HUMAN_REVIEW = "HUMAN_REVIEW"


# ---------------------------------------------------------------------------
# Identity & tenancy
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(200))
    auth_provider: Mapped[str] = mapped_column(String(40), default="password")
    role: Mapped[UserRole] = mapped_column(_enum(UserRole, "user_role"), default=UserRole.USER)
    preferred_language: Mapped[str] = mapped_column(String(5), default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    confidential_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    retention_policy: Mapped[str] = mapped_column(String(40), default="RETAIN_365_DAYS")
    external_retrieval_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    members: Mapped[list["WorkspaceMember"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[WorkspaceRole] = mapped_column(_enum(WorkspaceRole, "workspace_role"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    workspace: Mapped[Workspace] = relationship(back_populates="members")
    user: Mapped[User] = relationship()


# ---------------------------------------------------------------------------
# Innovations
# ---------------------------------------------------------------------------

class Innovation(Base):
    __tablename__ = "innovations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    innovation_type: Mapped[Optional[str]] = mapped_column(String(80))
    status: Mapped[InnovationStatus] = mapped_column(
        _enum(InnovationStatus, "innovation_status"), default=InnovationStatus.DRAFT
    )
    confidentiality_level: Mapped[Confidentiality] = mapped_column(
        _enum(Confidentiality, "confidentiality"), default=Confidentiality.INTERNAL
    )
    target_markets: Mapped[list] = mapped_column(JSONB, default=list)
    wizard_input: Mapped[dict] = mapped_column(JSONB, default=dict)
    analysis: Mapped[dict] = mapped_column(JSONB, default=dict)  # classification answers/results, run timestamps
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    profile: Mapped[Optional["InnovationProfile"]] = relationship(
        back_populates="innovation", uselist=False, cascade="all, delete-orphan"
    )
    features: Mapped[list["InnovationFeature"]] = relationship(
        back_populates="innovation", cascade="all, delete-orphan"
    )


class InnovationProfile(Base):
    __tablename__ = "innovation_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    innovation_id: Mapped[str] = mapped_column(ForeignKey("innovations.id", ondelete="CASCADE"), unique=True)
    ingredients: Mapped[list] = mapped_column(JSONB, default=list)
    botanical_names: Mapped[list] = mapped_column(JSONB, default=list)
    chemical_entities: Mapped[list] = mapped_column(JSONB, default=list)
    composition: Mapped[Optional[str]] = mapped_column(Text)
    process: Mapped[Optional[str]] = mapped_column(Text)
    extraction_method: Mapped[Optional[str]] = mapped_column(Text)
    dosage_form: Mapped[Optional[str]] = mapped_column(String(200))
    route: Mapped[Optional[str]] = mapped_column(String(100))
    intended_use: Mapped[Optional[str]] = mapped_column(Text)
    claims: Mapped[list] = mapped_column(JSONB, default=list)
    target_market: Mapped[list] = mapped_column(JSONB, default=list)
    manufacturing_location: Mapped[Optional[str]] = mapped_column(String(200))
    structured_features: Mapped[list] = mapped_column(JSONB, default=list)
    search_terms: Mapped[list] = mapped_column(JSONB, default=list)
    terminology: Mapped[list] = mapped_column(JSONB, default=list)
    assumptions: Mapped[list] = mapped_column(JSONB, default=list)
    missing_information: Mapped[list] = mapped_column(JSONB, default=list)
    ambiguities: Mapped[list] = mapped_column(JSONB, default=list)
    extraction_method_used: Mapped[str] = mapped_column(String(40), default="rules")
    user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    innovation: Mapped[Innovation] = relationship(back_populates="profile")


class InnovationFeature(Base):
    __tablename__ = "innovation_features"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    innovation_id: Mapped[str] = mapped_column(ForeignKey("innovations.id", ondelete="CASCADE"), index=True)
    feature_type: Mapped[FeatureType] = mapped_column(_enum(FeatureType, "feature_type"))
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text)
    normalized_term: Mapped[Optional[str]] = mapped_column(String(300))
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    source: Mapped[str] = mapped_column(String(40), default="USER_PROVIDED")

    innovation: Mapped[Innovation] = relationship(back_populates="features")


# ---------------------------------------------------------------------------
# Terminology
# ---------------------------------------------------------------------------

class Term(Base):
    __tablename__ = "terms"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    canonical: Mapped[str] = mapped_column(String(200), index=True)
    domain: Mapped[str] = mapped_column(String(60))
    english: Mapped[Optional[str]] = mapped_column(String(200))
    sanskrit: Mapped[Optional[str]] = mapped_column(String(200))
    hindi: Mapped[Optional[str]] = mapped_column(String(200))
    botanical: Mapped[Optional[str]] = mapped_column(String(200))
    chemical: Mapped[list] = mapped_column(JSONB, default=list)
    aliases: Mapped[list] = mapped_column(JSONB, default=list)
    ambiguity_note: Mapped[Optional[str]] = mapped_column(Text)
    candidate_species: Mapped[list] = mapped_column(JSONB, default=list)


# ---------------------------------------------------------------------------
# Sources & documents
# ---------------------------------------------------------------------------

class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(300))
    authority: Mapped[str] = mapped_column(String(200))
    authority_tier: Mapped[int] = mapped_column(Integer)
    jurisdiction: Mapped[str] = mapped_column(String(20), index=True)
    source_type: Mapped[str] = mapped_column(String(60))
    base_url: Mapped[Optional[str]] = mapped_column(String(500))
    access_level: Mapped[str] = mapped_column(String(40), default="PUBLIC")
    description: Mapped[Optional[str]] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    update_frequency_days: Mapped[int] = mapped_column(Integer, default=90, server_default="90")
    curator: Mapped[str] = mapped_column(String(200), default="Workspace admin", server_default="Workspace admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    document_type: Mapped[str] = mapped_column(String(60))  # LEGISLATION, RULES, GUIDANCE, PATENT, STUDY, TK_CONTEXT, USER_UPLOAD
    domain: Mapped[str] = mapped_column(String(60))  # IP, TK_ABS, REGULATORY, SCIENTIFIC
    jurisdiction: Mapped[str] = mapped_column(String(20), index=True)
    publication_date: Mapped[Optional[str]] = mapped_column(String(20))
    effective_date: Mapped[Optional[str]] = mapped_column(String(20))
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    version: Mapped[Optional[str]] = mapped_column(String(80))
    language: Mapped[str] = mapped_column(String(10), default="en")
    url: Mapped[Optional[str]] = mapped_column(String(800))
    access_level: Mapped[str] = mapped_column(String(40), default="PUBLIC")
    content_hash: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    extraction_method: Mapped[str] = mapped_column(String(40), default="STRUCTURED_SEED")
    ocr_confidence: Mapped[Optional[float]] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(40), default="DEMO_SEED")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    supersedes_document_id: Mapped[Optional[str]] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    superseded_by_document_id: Mapped[Optional[str]] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    source: Mapped[Source] = relationship()
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    section: Mapped[Optional[str]] = mapped_column(String(300))
    subsection: Mapped[Optional[str]] = mapped_column(String(300))
    chunk_type: Mapped[str] = mapped_column(String(40), default="PARAGRAPH")  # DEFINITION, CLAIM, ABSTRACT, RESULTS...
    content: Mapped[str] = mapped_column(Text)
    page_number: Mapped[Optional[int]] = mapped_column(Integer)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    injection_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding = mapped_column(Vector(settings.EMBEDDING_DIMENSION), nullable=True)
    search_vector = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(section,'') || ' ' || coalesce(subsection,'')), 'A') || "
            "setweight(to_tsvector('english', content), 'B')",
            persisted=True,
        ),
    )

    document: Mapped[Document] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("ix_chunks_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


# ---------------------------------------------------------------------------
# Domain records: patents, studies, regulatory pathways
# ---------------------------------------------------------------------------

class Patent(Base):
    __tablename__ = "patents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), unique=True)
    publication_number: Mapped[str] = mapped_column(String(60), index=True)
    application_number: Mapped[Optional[str]] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(500))
    abstract: Mapped[str] = mapped_column(Text)
    claims: Mapped[list] = mapped_column(JSONB, default=list)
    priority_date: Mapped[Optional[str]] = mapped_column(String(20))
    publication_date: Mapped[Optional[str]] = mapped_column(String(20))
    filing_date: Mapped[Optional[str]] = mapped_column(String(20))
    jurisdiction: Mapped[str] = mapped_column(String(20))
    applicant: Mapped[Optional[str]] = mapped_column(String(300))
    inventor: Mapped[list] = mapped_column(JSONB, default=list)
    patent_family_id: Mapped[Optional[str]] = mapped_column(String(60), index=True)
    classification_codes: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[Optional[str]] = mapped_column(String(60))

    document: Mapped[Document] = relationship()


class ScientificStudy(Base):
    __tablename__ = "scientific_studies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), unique=True)
    title: Mapped[str] = mapped_column(String(500))
    authors: Mapped[list] = mapped_column(JSONB, default=list)
    year: Mapped[Optional[int]] = mapped_column(Integer)
    journal: Mapped[Optional[str]] = mapped_column(String(300))
    study_type: Mapped[str] = mapped_column(String(80))
    population: Mapped[Optional[str]] = mapped_column(Text)
    intervention: Mapped[Optional[str]] = mapped_column(Text)
    dosage: Mapped[Optional[str]] = mapped_column(String(200))
    duration: Mapped[Optional[str]] = mapped_column(String(100))
    outcome: Mapped[Optional[str]] = mapped_column(Text)
    limitations: Mapped[Optional[str]] = mapped_column(Text)
    ingredients: Mapped[list] = mapped_column(JSONB, default=list)
    evidence_level: Mapped[str] = mapped_column(String(40), default="INGREDIENT")  # INGREDIENT | FORMULATION
    identifier: Mapped[Optional[str]] = mapped_column(String(100))

    document: Mapped[Document] = relationship()


class RegulatoryPathway(Base):
    __tablename__ = "regulatory_pathways"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    jurisdiction: Mapped[str] = mapped_column(String(20), index=True)
    product_category: Mapped[str] = mapped_column(String(200))
    category_key: Mapped[str] = mapped_column(String(80), index=True)
    authority: Mapped[str] = mapped_column(String(200))
    framework: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    requirements: Mapped[list] = mapped_column(JSONB, default=list)
    evidence_requirements: Mapped[list] = mapped_column(JSONB, default=list)
    quality_requirements: Mapped[list] = mapped_column(JSONB, default=list)
    safety_requirements: Mapped[list] = mapped_column(JSONB, default=list)
    claims_restrictions: Mapped[list] = mapped_column(JSONB, default=list)
    labeling_considerations: Mapped[list] = mapped_column(JSONB, default=list)
    triggers: Mapped[dict] = mapped_column(JSONB, default=dict)
    source_document_id: Mapped[Optional[str]] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    effective_date: Mapped[Optional[str]] = mapped_column(String(20))
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    source_document: Mapped[Optional[Document]] = relationship()


# ---------------------------------------------------------------------------
# Conversations & retrieval traces
# ---------------------------------------------------------------------------

class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    innovation_id: Mapped[Optional[str]] = mapped_column(ForeignKey("innovations.id", ondelete="SET NULL"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    language: Mapped[str] = mapped_column(String(5), default="en")
    mode: Mapped[str] = mapped_column(String(40), default="GENERAL")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)  # structured answer, citations, trace
    feedback: Mapped[Optional[str]] = mapped_column(String(20))
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RetrievalResult(Base):
    __tablename__ = "retrieval_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[Optional[str]] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[Optional[str]] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    query: Mapped[str] = mapped_column(Text)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_id: Mapped[str] = mapped_column(ForeignKey("document_chunks.id", ondelete="CASCADE"))
    retrieval_method: Mapped[str] = mapped_column(String(40))
    score: Mapped[float] = mapped_column(Float)
    rerank_score: Mapped[float] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ---------------------------------------------------------------------------
# Evidence, claims, verification
# ---------------------------------------------------------------------------

class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (UniqueConstraint("innovation_id", "chunk_id", "evidence_type"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    innovation_id: Mapped[str] = mapped_column(ForeignKey("innovations.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_id: Mapped[str] = mapped_column(ForeignKey("document_chunks.id", ondelete="CASCADE"))
    evidence_type: Mapped[str] = mapped_column(String(40))  # REGULATORY, IP, TK, SCIENTIFIC, PATENT
    relevance: Mapped[float] = mapped_column(Float)
    applicability: Mapped[str] = mapped_column(String(60))  # DIRECT, INGREDIENT_ONLY, CONTEXTUAL
    authority_tier: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)
    why_retrieved: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    added_by: Mapped[str] = mapped_column(String(20), default="SYSTEM")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    document: Mapped[Document] = relationship()
    chunk: Mapped[DocumentChunk] = relationship()


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[Optional[str]] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[Optional[str]] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    innovation_id: Mapped[Optional[str]] = mapped_column(ForeignKey("innovations.id", ondelete="CASCADE"), index=True)
    claim_text: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(40))  # FACT, INFERENCE, USER_PROVIDED, UNCERTAINTY
    risk_level: Mapped[Severity] = mapped_column(_enum(Severity, "severity"), default=Severity.LOW)
    support_status: Mapped[SupportStatus] = mapped_column(
        _enum(SupportStatus, "support_status"), default=SupportStatus.INSUFFICIENT
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[Optional[str]] = mapped_column(ForeignKey("document_chunks.id", ondelete="SET NULL"))
    evidence_id: Mapped[Optional[str]] = mapped_column(ForeignKey("evidence.id", ondelete="SET NULL"))
    support_status: Mapped[SupportStatus] = mapped_column(_enum(SupportStatus, "support_status"))
    entailment_score: Mapped[float] = mapped_column(Float)
    checks: Mapped[dict] = mapped_column(JSONB, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text)


class PatentFeatureMatch(Base):
    __tablename__ = "patent_feature_matches"
    __table_args__ = (UniqueConstraint("innovation_feature_id", "patent_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    innovation_id: Mapped[str] = mapped_column(ForeignKey("innovations.id", ondelete="CASCADE"), index=True)
    innovation_feature_id: Mapped[str] = mapped_column(ForeignKey("innovation_features.id", ondelete="CASCADE"))
    patent_id: Mapped[str] = mapped_column(ForeignKey("patents.id", ondelete="CASCADE"))
    chunk_id: Mapped[Optional[str]] = mapped_column(ForeignKey("document_chunks.id", ondelete="SET NULL"))
    match_type: Mapped[str] = mapped_column(String(40))
    similarity_score: Mapped[float] = mapped_column(Float)
    matched_passage: Mapped[str] = mapped_column(Text)
    matched_terms: Mapped[list] = mapped_column(JSONB, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    review_status: Mapped[str] = mapped_column(String(40), default="PENDING")

    feature: Mapped[InnovationFeature] = relationship()
    patent: Mapped[Patent] = relationship()


class EvidenceGap(Base):
    __tablename__ = "evidence_gaps"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    innovation_id: Mapped[str] = mapped_column(ForeignKey("innovations.id", ondelete="CASCADE"), index=True)
    gap_key: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[Severity] = mapped_column(_enum(Severity, "severity"))
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    recommended_action: Mapped[str] = mapped_column(Text)
    related: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Escalation(Base):
    __tablename__ = "escalations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    innovation_id: Mapped[str] = mapped_column(ForeignKey("innovations.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    type: Mapped[EscalationType] = mapped_column(_enum(EscalationType, "escalation_type"))
    reason: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    open_questions: Mapped[list] = mapped_column(JSONB, default=list)
    recommended_professional: Mapped[str] = mapped_column(String(200))
    packet: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[EscalationStatus] = mapped_column(
        _enum(EscalationStatus, "escalation_status"), default=EscalationStatus.OPEN
    )
    assigned_to: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewer_notes: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    innovation_id: Mapped[str] = mapped_column(ForeignKey("innovations.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[dict] = mapped_column(JSONB)
    markdown: Mapped[str] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[Optional[str]] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    source_id: Mapped[Optional[str]] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    document_id: Mapped[Optional[str]] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    file_name: Mapped[Optional[str]] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING RUNNING SUCCEEDED FAILED
    steps: Mapped[list] = mapped_column(JSONB, default=list)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class EvaluationQuestion(Base):
    __tablename__ = "evaluation_questions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    category: Mapped[str] = mapped_column(String(60))
    question: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(5), default="en")
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(20))
    expected_abstention: Mapped[bool] = mapped_column(Boolean, default=False)
    expected_document_titles: Mapped[list] = mapped_column(JSONB, default=list)
    expected_keywords: Mapped[list] = mapped_column(JSONB, default=list)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    metrics: Mapped[dict] = mapped_column(JSONB)
    results: Mapped[list] = mapped_column(JSONB)
    llm_provider: Mapped[str] = mapped_column(String(40))
    embedding_provider: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Feedback(Base):
    """Structured 'report an issue' on an answer, source or citation, with a review workflow."""
    __tablename__ = "feedback"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    message_id: Mapped[Optional[str]] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), index=True)
    innovation_id: Mapped[Optional[str]] = mapped_column(ForeignKey("innovations.id", ondelete="SET NULL"))
    category: Mapped[str] = mapped_column(String(40))  # WRONG_ANSWER WRONG_SOURCE CITATION_NOT_SUPPORTING OUTDATED_SOURCE UNSAFE OTHER
    reason: Mapped[str] = mapped_column(Text)
    target: Mapped[dict] = mapped_column(JSONB, default=dict)  # {key_point_id, chunk_id, citation_n}
    snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)  # answer + sources with versions at time of report
    status: Mapped[str] = mapped_column(String(20), default="OPEN")  # OPEN IN_REVIEW RESOLVED DISMISSED
    resolution_note: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[Optional[str]] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    entity_id: Mapped[Optional[str]] = mapped_column(String(36))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(80))
    request_id: Mapped[Optional[str]] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
