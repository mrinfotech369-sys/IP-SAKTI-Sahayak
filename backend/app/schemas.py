"""Request schemas (responses use the standard envelope with plain dict data)."""
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

Jurisdiction = Literal["IN", "US", "AU"]
Lang = Literal["en", "hi"]


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    organization: Optional[str] = Field(default=None, max_length=200)
    workspace: Optional[str] = Field(default=None, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    confidential_mode: bool = False
    retention_policy: str = Field(default="RETAIN_365_DAYS", max_length=40)


class WorkspacePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    confidential_mode: Optional[bool] = None
    retention_policy: Optional[str] = Field(default=None, max_length=40)
    external_retrieval_allowed: Optional[bool] = None


class MemberIn(BaseModel):
    email: EmailStr
    role: Literal["ADMIN", "RESEARCHER", "REVIEWER", "VIEWER"] = "RESEARCHER"


class IngredientIn(BaseModel):
    common_name: str = Field(default="", max_length=200)
    sanskrit_name: str = Field(default="", max_length=200)
    hindi_name: str = Field(default="", max_length=200)
    botanical_name: str = Field(default="", max_length=200)
    chemical_name: str = Field(default="", max_length=200)
    extract: str = Field(default="", max_length=300)
    quantity: str = Field(default="", max_length=100)
    source: str = Field(default="", max_length=200)


class WizardIn(BaseModel):
    basic: dict = Field(default_factory=dict)
    ingredients: list[IngredientIn] = Field(default_factory=list, max_length=40)
    formulation: dict = Field(default_factory=dict)
    process: dict = Field(default_factory=dict)
    claims: list[str] = Field(default_factory=list, max_length=30)
    markets: list[Jurisdiction] = Field(default_factory=list)
    confidentiality: Literal["PUBLIC_RESEARCH", "INTERNAL", "CONFIDENTIAL"] = "INTERNAL"

    @field_validator("basic", "formulation", "process")
    @classmethod
    def _flat_strings(cls, v: dict) -> dict:
        out = {}
        for k, val in v.items():
            if val is None:
                continue
            if not isinstance(val, str) or len(val) > 4000:
                raise ValueError(f"'{k}' must be text up to 4000 characters")
            out[str(k)[:60]] = val
        return out


class InnovationCreate(BaseModel):
    wizard: WizardIn
    generate_profile: bool = True
    run_analysis: bool = True
    acknowledge_confidentiality: bool = False


class InnovationPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=300)
    description: Optional[str] = Field(default=None, max_length=8000)
    status: Optional[Literal["DRAFT", "PROFILED", "IN_RESEARCH", "IN_REVIEW", "COMPLETED"]] = None
    confidentiality_level: Optional[Literal["PUBLIC_RESEARCH", "INTERNAL", "CONFIDENTIAL"]] = None
    target_markets: Optional[list[Jurisdiction]] = None


class ProfilePatch(BaseModel):
    ingredients: Optional[list[dict]] = None
    botanical_names: Optional[list[str]] = None
    chemical_entities: Optional[list[str]] = None
    composition: Optional[str] = None
    process: Optional[str] = None
    extraction_method: Optional[str] = None
    dosage_form: Optional[str] = None
    route: Optional[str] = None
    intended_use: Optional[str] = None
    claims: Optional[list[str]] = None
    target_market: Optional[list[Jurisdiction]] = None
    manufacturing_location: Optional[str] = None
    assumptions: Optional[list[str]] = None
    missing_information: Optional[list[str]] = None
    ambiguities: Optional[list[str]] = None
    features: Optional[list[dict]] = None
    confirm: bool = True


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: Optional[str] = None
    innovation_id: Optional[str] = None
    language: Optional[Lang] = None
    jurisdiction: Optional[Jurisdiction] = None
    mode: Optional[Literal["GENERAL", "INNOVATION", "PATENT", "SCIENTIFIC", "REGULATORY", "CROSS_JURISDICTION"]] = None
    filters: dict = Field(default_factory=dict)


class MessageFeedback(BaseModel):
    feedback: Optional[Literal["up", "down"]] = None
    flagged: Optional[bool] = None


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    jurisdictions: list[Jurisdiction] = Field(default_factory=list)
    domains: list[Literal["IP", "TK_ABS", "REGULATORY", "SCIENTIFIC"]] = Field(default_factory=list)
    document_types: list[str] = Field(default_factory=list)
    max_tier: Optional[int] = Field(default=None, ge=1, le=5)
    language: Optional[str] = None
    include_superseded: bool = False
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    top_k: int = Field(default=8, ge=1, le=25)
    innovation_id: Optional[str] = None


class VerifyIn(BaseModel):
    claim: str = Field(min_length=3, max_length=2000)
    chunk_id: Optional[str] = None
    jurisdictions: list[Jurisdiction] = Field(default_factory=list)


class ClassificationIn(BaseModel):
    answers: dict
    innovation_id: Optional[str] = None


class EvidenceAddIn(BaseModel):
    chunk_id: str
    evidence_type: Literal["REGULATORY", "IP", "TK", "SCIENTIFIC", "PATENT"] = "REGULATORY"
    notes: Optional[str] = Field(default=None, max_length=2000)


class GapPatch(BaseModel):
    status: Literal["OPEN", "ACKNOWLEDGED", "RESOLVED", "NOT_APPLICABLE"]


class MatchPatch(BaseModel):
    review_status: Literal["PENDING", "REVIEWED_RELEVANT", "REVIEWED_NOT_RELEVANT"]


class EscalationIn(BaseModel):
    innovation_id: str
    type: Literal["IP_REVIEW", "REGULATORY_REVIEW", "DOMAIN_REVIEW", "HUMAN_REVIEW"]
    reason: str = Field(min_length=3, max_length=2000)


class EscalationPatch(BaseModel):
    status: Literal["OPEN", "IN_REVIEW", "RESOLVED", "CLOSED"]


class ReportIn(BaseModel):
    innovation_id: str


class SourceIn(BaseModel):
    name: str = Field(min_length=2, max_length=300)
    authority: str = Field(min_length=2, max_length=200)
    authority_tier: int = Field(ge=1, le=5)
    jurisdiction: Literal["IN", "US", "AU", "INTERNATIONAL"]
    source_type: str = Field(max_length=60)
    base_url: Optional[str] = Field(default=None, max_length=500)
    access_level: Literal["PUBLIC", "RESTRICTED_RECORDS_PUBLIC_INFO", "WORKSPACE", "RESTRICTED"] = "PUBLIC"
    description: Optional[str] = Field(default=None, max_length=2000)
    active: bool = True


class DocumentReview(BaseModel):
    action: Literal["mark_checked", "approve", "mark_superseded"]
    superseded_by: Optional[str] = None
    version: Optional[str] = Field(default=None, max_length=80)
    effective_date: Optional[str] = Field(default=None, max_length=20)
    note: Optional[str] = Field(default=None, max_length=1000)


class FeedbackIn(BaseModel):
    message_id: Optional[str] = None
    innovation_id: Optional[str] = None
    category: Literal["WRONG_ANSWER", "WRONG_SOURCE", "CITATION_NOT_SUPPORTING", "OUTDATED_SOURCE", "UNSAFE", "OTHER"]
    reason: str = Field(min_length=3, max_length=2000)
    target: dict = Field(default_factory=dict)


class FeedbackPatch(BaseModel):
    status: Literal["OPEN", "IN_REVIEW", "RESOLVED", "DISMISSED"]
    resolution_note: Optional[str] = Field(default=None, max_length=2000)


class SourcePatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=300)
    authority: Optional[str] = Field(default=None, max_length=200)
    authority_tier: Optional[int] = Field(default=None, ge=1, le=5)
    base_url: Optional[str] = Field(default=None, max_length=500)
    access_level: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=2000)
    active: Optional[bool] = None
    update_frequency_days: Optional[int] = Field(default=None, ge=1, le=3650)
    curator: Optional[str] = Field(default=None, max_length=200)
    mark_checked: bool = False


class UserPatch(BaseModel):
    is_active: Optional[bool] = None
    role: Optional[Literal["ADMIN", "USER"]] = None
