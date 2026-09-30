"""Escalation packets and evidence reports (JSON + Markdown export)."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.orm import AuditLog, EscalationType, EvidenceGap, Innovation, Source
from app.services import analysis as analysis_svc
from app.services import evidence as evidence_svc
from app.services import patents as patent_svc
from app.services import regulatory as reg_svc
from app.services.verification import detect_conflicts, verify_claim
from app.services.verification import load_chunk

BOUNDARY = (
    "IP-SAKTI Sahayak is a decision-support and evidence-orchestration tool. It is not a patent agent, lawyer, "
    "regulator or medical advisor, does not create attorney-client privilege, and does not determine patentability, "
    "freedom to operate, regulatory approval or medical efficacy. Professional review is required."
)

PROFESSIONAL = {
    EscalationType.IP_REVIEW: "Registered patent agent / IP attorney",
    EscalationType.REGULATORY_REVIEW: "Regulatory affairs professional for the target market(s)",
    EscalationType.DOMAIN_REVIEW: "Ayurveda domain expert / pharmacognosist",
    EscalationType.HUMAN_REVIEW: "Qualified reviewer (IP, regulatory or domain as appropriate)",
}


def _profile(inn: Innovation) -> dict:
    p = inn.profile
    if not p:
        return {}
    return {
        "ingredients": p.ingredients, "botanical_names": p.botanical_names, "chemical_entities": p.chemical_entities,
        "composition": p.composition, "process": p.process, "extraction_method": p.extraction_method,
        "dosage_form": p.dosage_form, "route": p.route, "intended_use": p.intended_use, "claims": p.claims,
        "target_market": p.target_market, "manufacturing_location": p.manufacturing_location,
        "assumptions": p.assumptions, "missing_information": p.missing_information, "ambiguities": p.ambiguities,
        "user_confirmed": p.user_confirmed,
    }


def _audit(db: Session, inn: Innovation, limit: int = 40) -> list[dict]:
    rows = db.execute(
        select(AuditLog).where(AuditLog.workspace_id == inn.workspace_id, AuditLog.entity_id == inn.id)
        .order_by(AuditLog.created_at.desc()).limit(limit)
    ).scalars().all()
    return [{"action": r.action, "at": r.created_at.isoformat(), "user_id": r.user_id} for r in rows]


def _citation_checks(db: Session, evidence: list[dict], limit: int = 12) -> list[dict]:
    """Verify that each evidence item's stated relevance is supported by its passage."""
    out = []
    for e in evidence[:limit]:
        claim = e["passage"].split(". ")[0][:300]
        chunk = load_chunk(db, e["chunk_id"])
        v = verify_claim(claim, chunk, use_llm=False)
        out.append({"title": e["title"], "section": e["section"], "claim_checked": claim, "status": v["status"], "score": v["score"]})
    return out


def build_packet(db: Session, inn: Innovation) -> dict:
    ev = evidence_svc.evidence_list(db, inn)
    fm = patent_svc.feature_matrix(db, inn)
    sci = evidence_svc.scientific_cards(db, inn)
    pp = reg_svc.passport(db, inn, inn.workspace_id)
    gaps = [analysis_svc.gap_view(g) for g in db.execute(select(EvidenceGap).where(EvidenceGap.innovation_id == inn.id)).scalars()]
    conflicts = detect_conflicts([{"document_id": e["document_id"]} for e in ev], db)
    open_q = [g["description"] for g in gaps if g["status"] == "OPEN" and g["severity"] in ("HIGH", "CRITICAL")]
    for j, entry in pp["passport"].items():
        open_q += [f"[{j}] {q}" for q in entry["open_questions"][:3]]
    return {
        "innovation_summary": {
            "id": inn.id, "name": inn.name, "description": inn.description, "status": inn.status.value,
            "confidentiality": inn.confidentiality_level.value, "markets": inn.target_markets, "is_demo": inn.is_demo,
        },
        "structured_profile": _profile(inn),
        "technical_features": [{"type": f.feature_type.value, "name": f.name, "normalized": f.normalized_term, "source": f.source} for f in inn.features],
        "patent_findings": {"families": fm["families"], "matrix": fm["matrix"], "review_note": fm["review_note"]},
        "scientific_evidence": sci,
        "regulatory_findings": pp,
        "evidence_gaps": gaps,
        "conflicting_sources": conflicts,
        "open_questions": open_q,
        "citations": [{k: e[k] for k in ("title", "authority", "jurisdiction", "section", "url", "effective_date", "review_status", "is_demo")} for e in ev],
        "audit_trail": _audit(db, inn),
        "boundary": BOUNDARY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _md_list(items) -> str:
    items = [i for i in (items or []) if i]
    return "\n".join(f"- {i}" for i in items) if items else "- _None recorded_"


def build_report(db: Session, inn: Innovation) -> tuple[dict, str]:
    packet = build_packet(db, inn)
    ev = evidence_svc.evidence_list(db, inn)
    risks = analysis_svc.risk_map(db, inn)
    tk = evidence_svc.tk_context(db, inn, inn.workspace_id)
    from app.services.governance import provision_map
    provisions = provision_map(db, inn)["provisions"]
    summ = analysis_svc.summary(db, inn)
    comparison = reg_svc.comparison(packet["regulatory_findings"]["passport"])
    verification = _citation_checks(db, ev)
    sources = db.execute(select(Source).where(Source.active.is_(True)).order_by(Source.authority_tier)).scalars().all()
    high = [g for g in packet["evidence_gaps"] if g["severity"] in ("HIGH", "CRITICAL")]
    exec_summary = (
        f"{inn.name} was analysed against {len(ev)} evidence passages from configured sources across "
        f"{', '.join(packet['innovation_summary']['markets'] or ['no selected market'])}. "
        f"{len(packet['patent_findings']['families'])} patent families show feature-level overlap requiring professional review. "
        f"{len(high)} high/critical evidence gaps are open. All classifications are provisional."
    )
    content = {
        "title": f"Evidence Report — {inn.name}",
        "executive_summary": exec_summary,
        **packet,
        "tk_context": {k: tk[k] for k in ("tk_notice", "access_limitation", "attribution", "possible_overlap", "human_escalation")},
        "comparison": comparison,
        "risk_map": risks,
        "provision_map": provisions,
        "next_steps": summ["next_steps"],
        "limitations": [
            "Only configured sources were searched; absence of evidence is not evidence of absence.",
            "TKDL was not queried (restricted access); no TKDL prior-art conclusion is implied.",
            "Statute summaries are seed summaries to be verified against official text; demo patents are fictional.",
            "Confidence values are heuristic, not calibrated probabilities.",
            "Classifications are provisional and require professional review.",
        ],
        "source_versions": (inn.analysis or {}).get("history", [{}])[0].get("source_versions", []) if (inn.analysis or {}).get("history") else [],
        "citation_verification": verification,
        "source_registry": [{"name": s.name, "authority": s.authority, "tier": s.authority_tier, "jurisdiction": s.jurisdiction} for s in sources],
        "human_review_recommendations": [
            "IP review of the prior-art feature matrix before any public disclosure or filing.",
            "Regulatory review of the provisional category in each target market.",
            "Domain review of botanical identity for any ingredient flagged 'Needs confirmation'.",
        ],
    }
    p = packet["structured_profile"]
    md = [f"# {content['title']}", f"_Generated {packet['generated_at']}_", "", f"> {BOUNDARY}", ""]
    if inn.is_demo:
        md += ["> **DEMO DATA** — fictional innovation; patent records are fictional; statute summaries must be verified.", ""]
    md += ["## Executive Summary", exec_summary, "", "## Innovation Profile",
           f"- **Dosage form:** {p.get('dosage_form') or '—'}  \n- **Route:** {p.get('route') or '—'}  \n- **Intended use:** {p.get('intended_use') or '—'}",
           f"- **Markets:** {', '.join(p.get('target_market') or []) or '—'}",
           "", "**Ingredients**", _md_list([f"{i['name']} ({i.get('botanical_name') or i.get('normalized') or 'species not confirmed'}) — {i.get('status')}" for i in p.get("ingredients", [])]),
           "", "**Proposed claims (user-provided, not validated)**", _md_list(p.get("claims")),
           "", "## Classification (provisional)", _md_list([f"{c['country']}: {c['category']} (confidence {c['confidence']}; alternatives: {', '.join(c['alternatives']) or '—'})" for c in summ["classification"]]),
           "", "## Technical Features", _md_list([f"{f['type']}: {f['name']}" for f in packet["technical_features"]]),
           "", "## Traditional Knowledge Context", content["tk_context"]["tk_notice"], "", _md_list(content["tk_context"]["possible_overlap"]),
           f"\n_{content['tk_context']['access_limitation']}_",
           "", "## Scientific Evidence", f"_{packet['scientific_evidence']['notice']}_", ""]
    for c in packet["scientific_evidence"]["cards"]:
        md.append(f"- **{c['title']}** ({c['year']}, {c['study_type']}) — {c['outcome']}  \n  _Applicability:_ {c['applicability']}")
    md += ["", "## Patent / Prior-Art Findings", f"_{packet['patent_findings']['review_note']}_", ""]
    for fam in packet["patent_findings"]["families"]:
        r = fam["representative"]
        md.append(f"- **{r['title']}** — family {fam['family_id']} ({', '.join(fam['jurisdictions'])}); matched: {', '.join(fam['matched_features'])}; best similarity {fam['best_score']:.2f}")
    md += ["", "## Feature Matrix", "| Feature | Document | Date | Jurisdiction | Similarity | Review |", "|---|---|---|---|---|---|"]
    for m in packet["patent_findings"]["matrix"]:
        md.append(f"| {m['feature']} | {m['publication_number']} | {m['date'] or '—'} | {m['jurisdiction']} | {m['similarity']:.2f} | {m['review_status']} |")
    md += ["", "## Regulatory Passport"]
    for j, e in packet["regulatory_findings"]["passport"].items():
        pw = e.get("pathway") or {}
        md += [f"### {e['country']}", f"- **Possible pathway (provisional):** {e['possible_pathway']} (confidence {e['confidence']})",
               f"- **Authority:** {pw.get('authority', '—')}", f"- **Framework:** {pw.get('framework', '—')}", f"- **Freshness:** {e['freshness']}",
               "- **Requirements:**", _md_list(pw.get("requirements")), "- **Open questions:**", _md_list(e["open_questions"]), ""]
    md += ["## Jurisdiction Comparison", "| Dimension | India | USA | Australia |", "|---|---|---|---|"]
    for row in comparison:
        fmt = lambda v: "; ".join(v) if isinstance(v, list) else (v or "—")
        md.append(f"| {row['dimension']} | {fmt(row['IN'])} | {fmt(row['US'])} | {fmt(row['AU'])} |")
    md += ["", "## Provision Map (relevance flags, not legal determinations)",
           _md_list([f"[{x['severity']}] {x['jurisdiction']} · {x['instrument']} {x['provision']} — {x['issue']} _Why flagged:_ {x['why_flagged']}" for x in provisions])]
    md += ["", "## Evidence Gaps", _md_list([f"[{g['severity']}] {g['description']} → {g['recommended_action']}" for g in packet["evidence_gaps"]]),
           "", "## Risk Map", _md_list([f"**{r['category']}** ({r['severity']}): {r['risk']} — mitigation: {r['mitigation']} (owner: {r['owner']})" for r in risks]),
           "", "## Citation Verification", _md_list([f"{v['status']} — {v['title']} {v['section'] or ''}" for v in verification]),
           "", "## Conflicting Sources"]
    md.append(_md_list([f"{c['topic']}: {c['source_a']['title']} ({c['source_a']['position']}) vs {c['source_b']['title']} ({c['source_b']['position']}) — human review recommended" for c in packet["conflicting_sources"]]))
    md += ["", "## Next Steps", _md_list([f"[{n['severity']}] {n['action']} — because {n['because']}" for n in summ["next_steps"]])]
    md += ["", "## Open Questions", _md_list(packet["open_questions"]), "", "## Human Review Recommendations", _md_list(content["human_review_recommendations"]),
           "", "## Limitations", _md_list(content["limitations"]),
           "", "## Sources Cited", _md_list([f"{c['title']} — {c['authority']} ({c['jurisdiction']}) {c['section'] or ''} [{c['review_status']}]" for c in packet["citations"]]),
           "", "## Source Registry", _md_list([f"Tier {s['tier']} · {s['name']} ({s['jurisdiction']})" for s in content["source_registry"]]),
           "", "## Source Versions Used", _md_list([f"{v['title']} — version {v['version'] or '—'}, effective {v['effective_date'] or '—'}, last checked {v['last_checked'] or '—'}" for v in content["source_versions"]]),
           "", "## Audit Metadata", _md_list([f"{a['at']} — {a['action']}" for a in packet["audit_trail"][:20]]), ""]
    return content, "\n".join(md)
