"""Evidence gaps, risk map, evidence graph and the analysis orchestrator."""
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.orm import (
    Escalation,
    Evidence,
    EvidenceGap,
    Innovation,
    InnovationStatus,
    PatentFeatureMatch,
    Report,
    Severity,
)
from app.services import evidence as evidence_svc
from app.services import patents as patent_svc
from app.services import regulatory as reg_svc
from app.services.profile import DISEASE_WORDS
from app.services.verification import detect_conflicts

SEV_RANK = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_analysis(db: Session, inn: Innovation, workspace_id: str) -> dict:
    started = datetime.now(timezone.utc)
    steps = []
    ev = evidence_svc.discover(db, inn, workspace_id)
    steps.append({"step": "evidence_discovery", "counts": ev["counts"]})
    matches = patent_svc.match_innovation(db, inn, workspace_id)
    steps.append({"step": "patent_matching", "matches": len(matches)})
    state = dict(inn.analysis or {})
    answers = state.get("classification_answers") or reg_svc.defaults_from_profile(inn)
    cls = reg_svc.classify(db, answers, workspace_id)
    state["classification_answers"] = answers
    state["classification"] = cls
    steps.append({"step": "classification", "status": cls["status"]})
    inn.analysis = state
    db.flush()
    gaps = detect_gaps(db, inn)
    steps.append({"step": "gap_detection", "gaps": len(gaps)})
    state = dict(inn.analysis)
    state["last_run_at"] = datetime.now(timezone.utc).isoformat()
    state["last_run_steps"] = steps
    state["last_run_ms"] = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    # Reproducible trail: which source versions this run relied on.
    ev_docs = {e.document for e in db.execute(select(Evidence).where(Evidence.innovation_id == inn.id)).scalars()}
    run = {
        "at": state["last_run_at"], "latency_ms": state["last_run_ms"], "steps": steps,
        "source_versions": sorted(
            [{"title": d.title, "version": d.version, "effective_date": d.effective_date,
              "last_checked": d.last_checked.isoformat() if d.last_checked else None} for d in ev_docs],
            key=lambda x: x["title"]),
    }
    state["history"] = ([run] + list(state.get("history") or []))[:20]
    inn.analysis = state
    if inn.status in (InnovationStatus.DRAFT, InnovationStatus.PROFILED):
        inn.status = InnovationStatus.IN_RESEARCH
    db.flush()
    return {"steps": steps, "latency_ms": state["last_run_ms"]}


def completion(db: Session, inn: Innovation) -> dict:
    a = inn.analysis or {}
    checks = {
        "profile_generated": inn.profile is not None,
        "profile_confirmed": bool(inn.profile and inn.profile.user_confirmed),
        "evidence_discovered": db.execute(select(Evidence.id).where(Evidence.innovation_id == inn.id).limit(1)).first() is not None,
        "patents_searched": "last_run_at" in a,
        "classification_done": (a.get("classification") or {}).get("status") == "OK",
        "gaps_reviewed": db.execute(select(EvidenceGap.id).where(EvidenceGap.innovation_id == inn.id, EvidenceGap.status != "OPEN").limit(1)).first() is not None,
        "escalation_created": db.execute(select(Escalation.id).where(Escalation.innovation_id == inn.id).limit(1)).first() is not None,
        "report_generated": db.execute(select(Report.id).where(Report.innovation_id == inn.id).limit(1)).first() is not None,
    }
    return {"percent": round(100 * sum(checks.values()) / len(checks)), "checks": checks}


# ---------------------------------------------------------------------------
# Evidence gaps
# ---------------------------------------------------------------------------

def _gap(key, category, desc, sev, action, **related) -> dict:
    return {"gap_key": key, "category": category, "description": desc, "severity": sev, "recommended_action": action, "related": related}


def compute_gaps(db: Session, inn: Innovation) -> list[dict]:
    p = inn.profile
    gaps: list[dict] = []
    if not p:
        return [_gap("no-profile", "PROFILE", "Innovation profile has not been generated.", "HIGH", "Complete the innovation profiler.")]

    for ing in p.ingredients or []:
        if ing.get("status") == "NEEDS_CONFIRMATION" and not ing.get("botanical_name"):
            suggested = ing.get("normalized")
            desc = f"Botanical species for '{ing['name']}' is not confirmed" + (
                f" (terminology suggests {suggested})." if suggested else " and the common name is ambiguous."
            )
            gaps.append(_gap(f"species:{ing['name']}", "TERMINOLOGY", desc, "MEDIUM" if suggested else "HIGH",
                             "Confirm the botanical name (and voucher/authentication) for this ingredient.", ingredient=ing["name"]))
    if not (inn.target_markets or []):
        gaps.append(_gap("jurisdiction", "JURISDICTION", "Target jurisdiction is not selected.", "HIGH", "Select India, USA and/or Australia."))

    sci = evidence_svc.scientific_cards(db, inn)
    if not sci["formulation_evidence_found"]:
        gaps.append(_gap("formulation-evidence", "SCIENTIFIC", "Scientific evidence concerns individual ingredients, not the final formulation.", "HIGH",
                         "Plan formulation-level studies (e.g. pilot study) before making effect claims for the finished product."))
    for name in sci["ingredients_without_evidence"]:
        gaps.append(_gap(f"no-science:{name}", "SCIENTIFIC", f"No configured scientific evidence found for '{name}'.", "MEDIUM",
                         "Search additional scientific sources or ingest relevant studies.", ingredient=name))

    for c in p.claims or []:
        if DISEASE_WORDS.search(c):
            gaps.append(_gap(f"claim-disease:{c[:60]}", "CLAIMS", f"Proposed claim may be a disease/treatment claim: \"{c}\".", "CRITICAL",
                             "Revise to a permitted structure/function or traditional indication, or plan for a drug pathway.", claim=c))
        else:
            gaps.append(_gap(f"claim-support:{c[:60]}", "CLAIMS", f"No configured authoritative source directly supports the proposed claim \"{c}\" for this formulation.", "MEDIUM",
                             "Hold substantiation for the claim (formulation-level evidence) before use.", claim=c))

    cls = (inn.analysis or {}).get("classification") or {}
    for j, res in (cls.get("results") or {}).items():
        if res.get("ambiguous"):
            gaps.append(_gap(f"classification:{j}", "CLASSIFICATION", f"Product category in {res['jurisdiction_name']} depends on intended use and positioning ({', '.join(c['category'] for c in res['candidates'][:2])}).",
                             "MEDIUM", "Answer the classification questions and obtain regulatory review.", jurisdiction=j))
        for q in res.get("missing_questions", []):
            gaps.append(_gap(f"missing:{j}:{q[:40]}", "CLASSIFICATION", f"{res['jurisdiction_name']}: missing information — {q}.", "LOW", "Provide this information in the classification questionnaire.", jurisdiction=j))

    matches = db.execute(select(PatentFeatureMatch).where(PatentFeatureMatch.innovation_id == inn.id)).scalars().all()
    if matches:
        top = max(m.similarity_score for m in matches)
        fams = {m.patent.patent_family_id for m in matches}
        gaps.append(_gap("patent-review", "IP", f"{len(matches)} feature-level overlaps across {len(fams)} patent families require professional interpretation.",
                         "HIGH" if top >= 0.5 else "MEDIUM", "Request IP review of the feature matrix before disclosure or filing.", top_similarity=round(top, 3)))

    if "US" in (inn.target_markets or []) and (p.extraction_method or p.process):
        gaps.append(_gap("us-ndi", "REGULATORY", "Novel extraction process may create a New Dietary Ingredient (US) — NDI status not assessed.", "MEDIUM",
                         "Assess NDI status and whether a 75-day premarket notification is needed.", jurisdiction="US"))
    if "IN" in (inn.target_markets or []) or any(i.get("source", "") and "india" in (i.get("source") or "").lower() for i in p.ingredients or []):
        gaps.append(_gap("nba-approval", "TK_ABS", "If a patent is sought for an invention based on Indian biological resources, NBA approval (Biological Diversity Act s.6) must be considered.", "MEDIUM",
                         "Confirm sourcing and plan NBA approval / benefit-sharing before IPR grant.", jurisdiction="IN"))

    evs = db.execute(select(Evidence).where(Evidence.innovation_id == inn.id)).scalars().all()
    stale = sorted({e.document.title for e in evs if e.document.superseded_by_document_id or (e.document.last_checked and (datetime.now(timezone.utc) - e.document.last_checked).days > 180)})
    for t in stale:
        gaps.append(_gap(f"stale:{t[:60]}", "FRESHNESS", f"Source is potentially outdated or superseded: {t}.", "LOW", "Re-check the source against the official current version.", title=t))
    conflicts = detect_conflicts([{"document_id": e.document_id} for e in evs], db)
    for c in conflicts:
        gaps.append(_gap(f"conflict:{c['topic']}", "CONFLICT", f"Conflicting sources on '{c['topic']}': {c['source_a']['title']} vs {c['source_b']['title']}.", "HIGH",
                         "Human review required to resolve which source applies.", conflict=c))
    if inn.confidentiality_level.value == "CONFIDENTIAL":
        gaps.append(_gap("confidential", "DATA", "Confidential innovation — avoid unnecessary disclosure of unpublished details in external searches.", "LOW",
                         "Keep searches to configured internal sources; review before sharing reports."))
    for m in p.missing_information or []:
        if "Quantity" in m or "Plant part" in m:
            gaps.append(_gap(f"profile:{m[:60]}", "PROFILE", m, "LOW", "Complete the innovation profile."))
    return gaps


def detect_gaps(db: Session, inn: Innovation) -> list[EvidenceGap]:
    previous = {g.gap_key: g.status for g in db.execute(select(EvidenceGap).where(EvidenceGap.innovation_id == inn.id)).scalars()}
    db.execute(delete(EvidenceGap).where(EvidenceGap.innovation_id == inn.id))
    seen, rows = set(), []
    for g in compute_gaps(db, inn):
        if g["gap_key"] in seen:
            continue
        seen.add(g["gap_key"])
        row = EvidenceGap(innovation_id=inn.id, severity=Severity(g["severity"]), status=previous.get(g["gap_key"], "OPEN"),
                          **{k: v for k, v in g.items() if k != "severity"})
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def gap_view(g: EvidenceGap) -> dict:
    return {"id": g.id, "gap_key": g.gap_key, "category": g.category, "description": g.description, "severity": g.severity.value,
            "status": g.status, "recommended_action": g.recommended_action, "related": g.related}


# ---------------------------------------------------------------------------
# Risk map
# ---------------------------------------------------------------------------

RISK_CATEGORIES = {
    "IP Risk": (["IP", "TK_ABS"], "Overlapping prior art or TK-based exclusions (Patents Act s.3(p)) can affect patent strategy.", "Patent agent / IP counsel"),
    "Regulatory Risk": (["REGULATORY"], "Wrong pathway or missing notifications can block market entry.", "Regulatory affairs"),
    "Evidence Risk": (["SCIENTIFIC", "CLAIMS"], "Claims without formulation-level evidence risk enforcement and credibility loss.", "Scientific lead"),
    "Data Risk": (["DATA"], "Incomplete or unverified data propagates into every downstream decision.", "Innovation owner"),
    "Confidentiality Risk": (["DATA"], "Premature disclosure can destroy novelty.", "Innovation owner"),
    "Source Freshness Risk": (["FRESHNESS", "CONFLICT"], "Outdated or conflicting sources may misstate current requirements.", "Workspace admin"),
    "Translation Risk": (["TERMINOLOGY"], "Ambiguous common/Sanskrit names can map to the wrong species.", "Domain expert (Ayurveda/botany)"),
    "Classification Risk": (["CLASSIFICATION", "JURISDICTION"], "Category depends on claims and positioning, which drive all requirements.", "Regulatory affairs"),
}


def risk_map(db: Session, inn: Innovation) -> list[dict]:
    gaps = db.execute(select(EvidenceGap).where(EvidenceGap.innovation_id == inn.id)).scalars().all()
    out = []
    for name, (cats, why, owner) in RISK_CATEGORIES.items():
        related = [g for g in gaps if g.category in cats]
        if name == "Confidentiality Risk":
            related = [g for g in related if g.gap_key == "confidential"]
        elif name == "Data Risk":
            related = [g for g in gaps if g.category == "PROFILE"]
        if not related:
            out.append({"category": name, "risk": "No open items detected", "severity": "LOW", "evidence": [], "why_it_matters": why,
                        "mitigation": "Re-run analysis after profile changes.", "open_question": None, "owner": owner, "count": 0})
            continue
        worst = max(related, key=lambda g: SEV_RANK[g.severity.value])
        out.append({
            "category": name,
            "risk": worst.description,
            "severity": worst.severity.value,
            "evidence": [g.description for g in related[:5]],
            "why_it_matters": why,
            "mitigation": worst.recommended_action,
            "open_question": next((g.description for g in related if g.status == "OPEN"), None),
            "owner": owner,
            "count": len(related),
        })
    out.sort(key=lambda r: -SEV_RANK[r["severity"]])
    return out


# ---------------------------------------------------------------------------
# Evidence graph
# ---------------------------------------------------------------------------

def evidence_graph(db: Session, inn: Innovation) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def node(nid, ntype, label, **data):
        nodes.setdefault(nid, {"id": nid, "type": ntype, "label": label, "data": data})

    def edge(src, dst, etype, provenance: dict):
        edges.append({"id": f"e{len(edges)}", "source": src, "target": dst, "type": etype, "provenance": provenance})

    inn_id = f"innovation:{inn.id}"
    node(inn_id, "Innovation", inn.name, status=inn.status.value)

    for f in inn.features:
        ntype = "Ingredient" if f.feature_type.value == "INGREDIENT" else ("Claim" if f.feature_type.value == "CLAIM" else "Feature")
        fid = f"feature:{f.id}"
        node(fid, ntype, f.name, feature_type=f.feature_type.value, normalized=f.normalized_term, source=f.source)
        edge(fid, inn_id, "FEATURE_OF", {"source": "Innovation profile", "detail": f"{f.feature_type.value} ({f.source})"})

    ing_nodes = {f.name.lower(): f"feature:{f.id}" for f in inn.features if f.feature_type.value == "INGREDIENT"}
    for m in db.execute(select(PatentFeatureMatch).where(PatentFeatureMatch.innovation_id == inn.id)).scalars():
        pid = f"patent:{m.patent_id}"
        node(pid, "Patent", m.patent.publication_number, title=m.patent.title, family=m.patent.patent_family_id, is_demo=m.patent.document.is_demo)
        edge(f"feature:{m.innovation_feature_id}", pid, "SIMILAR_TO",
             {"source": m.patent.title, "passage": m.matched_passage[:400], "score": round(m.similarity_score, 3), "chunk_id": m.chunk_id})
        edge(pid, inn_id, "REQUIRES_REVIEW", {"source": "Patent feature matrix", "detail": patent_svc.REVIEW_NOTE})

    sci = evidence_svc.scientific_cards(db, inn)
    for c in sci["cards"]:
        sid = f"study:{c['id']}"
        node(sid, "Scientific Study", f"{(c['authors'] or ['?'])[0]} {c['year']}", title=c["title"], level=c["evidence_level"])
        linked = False
        for ing_name in c["relevant_ingredients"]:
            for key, nid in ing_nodes.items():
                if ing_name in key or key in ing_name:
                    edge(nid, sid, "HAS_EVIDENCE", {"source": c["title"], "detail": c["applicability"]})
                    linked = True
        if not linked:
            edge(inn_id, sid, "HAS_EVIDENCE", {"source": c["title"], "detail": c["applicability"]})

    for e in evidence_svc.evidence_list(db, inn):
        if e["evidence_type"] == "TK":
            tid = f"doc:{e['document_id']}"
            node(tid, "Traditional Knowledge Context", e["title"][:60], title=e["title"], section=e["section"])
            edge(inn_id, tid, "MENTIONED_IN", {"source": e["title"], "passage": e["passage"][:300], "section": e["section"]})
        elif e["evidence_type"] == "IP":
            rid = f"doc:{e['document_id']}"
            node(rid, "Regulation", e["title"][:60], title=e["title"], section=e["section"])
            edge(rid, inn_id, "APPLIES_TO", {"source": e["title"], "passage": e["passage"][:300], "section": e["section"]})

    passport = reg_svc.passport(db, inn, inn.workspace_id)["passport"]
    for j, entry in passport.items():
        jid = f"jurisdiction:{j}"
        node(jid, "Jurisdiction", entry["country"])
        pw = entry.get("pathway")
        if pw:
            aid = f"authority:{pw['authority']}"
            node(aid, "Authority", pw["authority"])
            edge(inn_id, aid, "REGULATED_BY", {"source": "Provisional classification", "detail": f"{entry['possible_pathway']} (confidence {entry['confidence']})"})
            edge(aid, jid, "APPLIES_TO", {"source": pw["framework"]})
            if pw.get("source_document"):
                sd = pw["source_document"]
                rid = f"doc:{sd['id']}"
                node(rid, "Regulation", sd["title"][:60], title=sd["title"], url=sd["url"])
                edge(rid, jid, "APPLIES_TO", {"source": sd["title"], "detail": pw["framework"]})
                edge(inn_id, rid, "SUPPORTED_BY", {"source": sd["title"], "detail": "Pathway source document"})

    for g in db.execute(select(EvidenceGap).where(EvidenceGap.innovation_id == inn.id)).scalars():
        if g.severity.value in ("HIGH", "CRITICAL"):
            gid = f"gap:{g.id}"
            node(gid, "Evidence Gap", g.description[:60], severity=g.severity.value, description=g.description)
            edge(inn_id, gid, "HAS_GAP", {"source": "Evidence gap detector", "detail": g.recommended_action})
            claim = (g.related or {}).get("claim")
            if claim:
                for f in inn.features:
                    if f.feature_type.value == "CLAIM" and f.description == claim:
                        edge(f"feature:{f.id}", gid, "REQUIRES_REVIEW", {"source": "Claims check", "detail": g.description})

    return {"nodes": list(nodes.values()), "edges": edges}


# ---------------------------------------------------------------------------
# Structured summary: Classification → Regulatory Pathway → IP Considerations → Evidence → Next Steps
# ---------------------------------------------------------------------------

def summary(db: Session, inn: Innovation) -> dict:
    from app.services.governance import provision_map

    pp = reg_svc.passport(db, inn, inn.workspace_id)
    provs = provision_map(db, inn)["provisions"]
    ev = evidence_svc.evidence_list(db, inn)
    gaps = db.execute(select(EvidenceGap).where(EvidenceGap.innovation_id == inn.id)).scalars().all()
    fm = patent_svc.feature_matrix(db, inn)
    by_type: dict[str, int] = {}
    for e in ev:
        by_type[e["evidence_type"]] = by_type.get(e["evidence_type"], 0) + 1
    open_high = sorted([g for g in gaps if g.status == "OPEN" and g.severity.value in ("HIGH", "CRITICAL")], key=lambda g: -SEV_RANK[g.severity.value])
    next_steps = [{"action": g.recommended_action, "because": g.description, "severity": g.severity.value} for g in open_high[:6]]
    if fm["families"]:
        next_steps.append({"action": "Request IP review of the prior-art feature matrix before any disclosure or filing.",
                           "because": f"{len(fm['families'])} patent families overlap with innovation features.", "severity": "HIGH"})
    next_steps.append({"action": "Request regulatory review of the provisional category in each market.",
                       "because": "All classifications are provisional.", "severity": "MEDIUM"})
    return {
        "classification": [
            {"jurisdiction": j, "country": e["country"], "category": e["possible_pathway"], "confidence": e["confidence"],
             "alternatives": e["alternatives"], "human_review_required": True}
            for j, e in pp["passport"].items()
        ],
        "regulatory_pathway": [
            {"jurisdiction": j, "country": e["country"], "authority": (e["pathway"] or {}).get("authority"),
             "framework": (e["pathway"] or {}).get("framework"), "key_requirements": ((e["pathway"] or {}).get("requirements") or [])[:3],
             "freshness": e["freshness"], "open_questions": e["open_questions"][:3]}
            for j, e in pp["passport"].items()
        ],
        "ip_considerations": {
            "provisions": [x for x in provs if x["area"] in ("IP", "TK_ABS")],
            "patent_families": len(fm["families"]),
            "feature_overlaps": len(fm["matrix"]),
            "tkdl_access": {"status": "RESTRICTED_NOT_QUERIED", "label": "TKDL access: restricted — not queried"},
            "boundary": "Relevance flags only — not a patentability or freedom-to-operate determination.",
        },
        "evidence": {"total": len(ev), "by_type": by_type, "top": ev[:4]},
        "next_steps": next_steps,
        "history": (inn.analysis or {}).get("history", [])[:5],
    }
