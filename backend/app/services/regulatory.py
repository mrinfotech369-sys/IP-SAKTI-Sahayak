"""Product classification assistant + regulatory navigator/passport.

Every category is *provisional*: the output lists assumptions, facts that
could change the result, open questions, and always requires human review.
"""
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.orm import Innovation, RegulatoryPathway
from app.services.retrieval import RetrievalFilters, freshness_status, retrieve

JUR_NAMES = {"IN": "India", "US": "USA", "AU": "Australia"}
DISEASE = re.compile(r"\b(treat\w*|cure\w*|prevent\w*|mitigat\w*|disease|disorder|diabetes|cancer|hypertension|arthritis|depression|infection)\b", re.I)
HIGH_LEVEL = re.compile(r"\b(disorder|disease|diabetes|cancer|hypertension|depression|infection)\b", re.I)
SUPPORTIVE = re.compile(r"\b(support\w*|maintain\w*|promot\w*|healthy|well-?being|general health|relief of|helps?)\b", re.I)

QUESTIONS = [
    {"key": "product", "label": "What is the product?", "type": "text"},
    {"key": "ingredients", "label": "What are the ingredients?", "type": "text"},
    {"key": "source", "label": "What is the source of the ingredients?", "type": "select", "options": ["Plant", "Animal", "Mineral", "Mixed"]},
    {"key": "dosage_form", "label": "What is the dosage form?", "type": "text"},
    {"key": "route", "label": "What is the route?", "type": "select", "options": ["Oral", "Topical", "Parenteral", "Other"]},
    {"key": "intended_use", "label": "What is the intended use?", "type": "text"},
    {"key": "claims", "label": "What claims will appear on label or marketing?", "type": "list"},
    {"key": "markets", "label": "Where will it be marketed?", "type": "multi", "options": ["IN", "US", "AU"]},
    {"key": "manufacturing", "label": "How will it be manufactured?", "type": "text"},
    {"key": "classical_formula", "label": "Is it exactly a formulation from an authoritative Ayurvedic text?", "type": "select", "options": ["yes", "no", "unsure"]},
    {"key": "food_positioning", "label": "Will it be positioned as a food / supplement rather than a medicine?", "type": "select", "options": ["yes", "no", "unsure"]},
    {"key": "purified_fraction", "label": "Is the active a purified fraction with defined chemical markers?", "type": "select", "options": ["yes", "no", "unsure"]},
]


def defaults_from_profile(inn: Innovation) -> dict:
    p = inn.profile
    if not p:
        return {"markets": inn.target_markets or []}
    return {
        "product": inn.name,
        "ingredients": ", ".join(i.get("name", "") for i in p.ingredients or []),
        "source": "Plant",
        "dosage_form": p.dosage_form or "",
        "route": p.route or "",
        "intended_use": p.intended_use or "",
        "claims": p.claims or [],
        "markets": p.target_market or inn.target_markets or [],
        "manufacturing": p.manufacturing_location or "",
        "classical_formula": "no" if (p.extraction_method or p.process) else "unsure",
        "food_positioning": "unsure",
        "purified_fraction": "no",
    }


def _claims_text(a: dict) -> str:
    c = a.get("claims") or []
    return " ".join(c) if isinstance(c, list) else str(c)


def _cand(key: str, conf: float, why: str) -> dict:
    return {"key": key, "confidence": round(min(conf, 0.75), 2), "why": why}


def classify_jurisdiction(j: str, a: dict) -> dict:
    claims = _claims_text(a)
    use = a.get("intended_use", "")
    disease = bool(DISEASE.search(claims) or DISEASE.search(use))
    high = bool(HIGH_LEVEL.search(claims))
    supportive = bool(SUPPORTIVE.search(claims + " " + use))
    route = (a.get("route") or "").lower()
    classical, food, purified = a.get("classical_formula"), a.get("food_positioning"), a.get("purified_fraction")
    cands, assumptions, changers, missing = [], [], [], []

    if not route:
        missing.append("Route of administration")
    if not claims:
        missing.append("Proposed label/marketing claims")
    if route == "parenteral":
        assumptions.append("Parenteral route falls outside ASU P&P and food categories.")

    if j == "IN":
        if purified == "yes":
            cands.append(_cand("IN_PHYTOPHARMA", 0.6, "Purified, marker-defined fraction suggests the phytopharmaceutical (new drug) pathway."))
        if classical == "yes":
            cands.append(_cand("IN_ASU_CLASSICAL", 0.7 if food != "yes" else 0.45,
                               "Formulation stated to follow an authoritative text exactly." + (" Food positioning makes the Aahara route more likely." if food == "yes" else "")))
        if food == "yes":
            cands.append(_cand("IN_AYURVEDA_AAHARA" if classical == "yes" else "IN_HEALTH_SUPPLEMENT", 0.55,
                               "Food/supplement positioning without therapeutic claims."))
        if classical != "yes" and purified != "yes" and route != "parenteral":
            conf = 0.65 if (disease or food != "yes") else 0.4
            cands.append(_cand("IN_ASU_PP", conf, "Ayurvedic ingredients combined in a non-classical formulation / process (s.3(h))."))
        if food != "yes" and not any(c["key"] == "IN_HEALTH_SUPPLEMENT" for c in cands):
            cands.append(_cand("IN_HEALTH_SUPPLEMENT", 0.3 if not disease else 0.1,
                               "Possible only if positioned as food with permitted botanicals and no disease claims."))
        changers += [
            "Whether the formulation exactly matches an authoritative Ayurvedic text (classical vs P&P).",
            "Positioning as a medicine vs a food/health supplement.",
            "Any disease-treatment claim (also restricted by the Drugs and Magic Remedies Act).",
            "Whether the process yields a purified, marker-defined fraction (phytopharmaceutical).",
        ]
        if classical == "unsure":
            missing.append("Confirm whether the formulation is from an authoritative text")
        if food == "unsure":
            missing.append("Confirm medicine vs food positioning")
    elif j == "US":
        if disease:
            cands.append(_cand("US_BOTANICAL_DRUG", 0.65, "Disease-related claims make the product a drug by intended use (21 U.S.C. 321(g)(1))."))
            cands.append(_cand("US_DIETARY_SUPPLEMENT", 0.3, "Possible only if disease claims are removed and structure/function claims are used."))
        elif route in ("oral", ""):
            cands.append(_cand("US_DIETARY_SUPPLEMENT", 0.65 if supportive else 0.5, "Oral botanical product with structure/function-type claims."))
        assumptions.append("Novel extraction may create a 'new dietary ingredient' requiring NDI notification — to be assessed.")
        changers += ["Disease claims anywhere in labeling or marketing.", "Whether ingredients are 'new dietary ingredients' (post-1994 / chemically altered)."]
    elif j == "AU":
        if high or disease:
            cands.append(_cand("AU_REGISTERED_CM", 0.55, "Higher-level (disease) indications require registration and TGA evaluation."))
            cands.append(_cand("AU_LISTED", 0.25, "Possible only with permitted low-level indications."))
        else:
            cands.append(_cand("AU_LISTED", 0.6, "Low-level indications with permitted ingredients suggest listing (s.26A)."))
            cands.append(_cand("AU_ASSESSED_LISTED", 0.25, "If intermediate-level indications are sought."))
        assumptions.append("All ingredients are assumed to be on the permitted ingredients list — must be checked.")
        changers += ["Indication level (low / intermediate / high).", "Whether each ingredient is a permitted ingredient.", "Traditional-use indications must name the Ayurvedic tradition."]

    cands.sort(key=lambda c: -c["confidence"])
    return {"candidates": cands, "assumptions": assumptions, "facts_that_could_change": changers, "missing_questions": missing}


def _pathway(db: Session, key: str) -> Optional[RegulatoryPathway]:
    return db.execute(select(RegulatoryPathway).where(RegulatoryPathway.category_key == key)).scalar_one_or_none()


def pathway_view(pw: RegulatoryPathway) -> dict:
    d = pw.source_document
    return {
        "key": pw.category_key,
        "jurisdiction": pw.jurisdiction,
        "category": pw.product_category,
        "authority": pw.authority,
        "framework": pw.framework,
        "description": pw.description,
        "requirements": pw.requirements,
        "evidence_requirements": pw.evidence_requirements,
        "quality_requirements": pw.quality_requirements,
        "safety_requirements": pw.safety_requirements,
        "claims_considerations": pw.claims_restrictions,
        "labeling_considerations": pw.labeling_considerations,
        "effective_date": pw.effective_date or (d.effective_date if d else None),
        "source_document": {
            "id": d.id, "title": d.title, "url": d.url, "authority": d.source.authority, "tier": d.source.authority_tier,
            "review_status": d.review_status, "is_demo": d.is_demo,
        } if d else None,
        "freshness": freshness_status(d.last_checked if d else None, bool(d and d.superseded_by_document_id)),
        "last_checked": d.last_checked.isoformat() if d and d.last_checked else None,
    }


def classify(db: Session, answers: dict, workspace_id: str) -> dict:
    markets = [m for m in (answers.get("markets") or []) if m in JUR_NAMES]
    if not markets:
        return {
            "status": "NEEDS_INPUT",
            "message": "Which market are you evaluating? Select India, USA and/or Australia.",
            "questions": QUESTIONS,
        }
    results = {}
    for j in markets:
        c = classify_jurisdiction(j, answers)
        for cand in c["candidates"]:
            pw = _pathway(db, cand["key"])
            cand["category"] = pw.product_category if pw else cand["key"]
            cand["authority"] = pw.authority if pw else None
            cand["framework"] = pw.framework if pw else None
        q = f"{answers.get('dosage_form', '')} {answers.get('intended_use', '')} {_claims_text(answers)} product category definition"
        r = retrieve(db, q, filters=RetrievalFilters(jurisdictions=[j], domains=["REGULATORY"], workspace_id=workspace_id),
                     intent="PRODUCT_CLASSIFICATION", top_k=4)
        top = c["candidates"][0] if c["candidates"] else None
        close = len(c["candidates"]) > 1 and top and (top["confidence"] - c["candidates"][1]["confidence"]) < 0.2
        results[j] = {
            "jurisdiction": j,
            "jurisdiction_name": JUR_NAMES[j],
            "provisional_category": top["category"] if top else None,
            "provisional_key": top["key"] if top else None,
            "confidence": top["confidence"] if top else 0.0,
            "candidates": c["candidates"],
            "assumptions": c["assumptions"],
            "facts_that_could_change": c["facts_that_could_change"],
            "missing_questions": c["missing_questions"],
            "ambiguous": bool(close),
            "evidence": [
                {k: x[k] for k in ("chunk_id", "document_id", "title", "authority", "tier", "section", "content", "why_retrieved", "freshness", "is_demo")}
                for x in r.results
            ],
            "human_review_required": True,
            "label": "Provisional classification — not a legal determination.",
        }
    return {"status": "OK", "answers": answers, "results": results, "generated_at": datetime.now(timezone.utc).isoformat()}


def passport(db: Session, inn: Innovation, workspace_id: str) -> dict:
    state = inn.analysis or {}
    cls = state.get("classification")
    if not cls or cls.get("status") != "OK":
        cls = classify(db, state.get("classification_answers") or defaults_from_profile(inn), workspace_id)
    entries = {}
    results = cls.get("results") or {}
    for j, res in sorted(results.items(), key=lambda kv: ["IN", "US", "AU"].index(kv[0]) if kv[0] in ("IN", "US", "AU") else 9):
        pw = _pathway(db, res["provisional_key"]) if res.get("provisional_key") else None
        view = pathway_view(pw) if pw else None
        open_q = list(res["missing_questions"]) + [f"Confirm: {x}" for x in res["facts_that_could_change"][:2]]
        entries[j] = {
            "country": JUR_NAMES[j],
            "jurisdiction": j,
            "possible_pathway": res["provisional_category"],
            "confidence": res["confidence"],
            "alternatives": [c["category"] for c in res["candidates"][1:]],
            "pathway": view,
            "assumptions": res["assumptions"],
            "open_questions": open_q,
            "evidence": res["evidence"],
            "freshness": view["freshness"] if view else "Unknown",
            "human_review_required": True,
        }
    return {"classification": cls, "passport": entries}


COMPARISON_DIMENSIONS = [
    ("Possible category", lambda e: e["possible_pathway"]),
    ("Authority", lambda e: e["pathway"]["authority"] if e["pathway"] else None),
    ("Key sources", lambda e: e["pathway"]["framework"] if e["pathway"] else None),
    ("Evidence requirements", lambda e: e["pathway"]["evidence_requirements"] if e["pathway"] else None),
    ("Claims considerations", lambda e: e["pathway"]["claims_considerations"] if e["pathway"] else None),
    ("Quality", lambda e: e["pathway"]["quality_requirements"] if e["pathway"] else None),
    ("Safety", lambda e: e["pathway"]["safety_requirements"] if e["pathway"] else None),
    ("Labeling", lambda e: e["pathway"]["labeling_considerations"] if e["pathway"] else None),
    ("Open questions", lambda e: e["open_questions"]),
    ("Freshness", lambda e: e["freshness"]),
    ("Human review", lambda e: "Required"),
]


def comparison(passport_entries: dict) -> list[dict]:
    rows = []
    for name, fn in COMPARISON_DIMENSIONS:
        rows.append({"dimension": name, **{j: (fn(passport_entries[j]) if j in passport_entries else None) for j in ("IN", "US", "AU")}})
    return rows


def jurisdiction_overview(db: Session, j: str) -> dict:
    pws = db.execute(select(RegulatoryPathway).where(RegulatoryPathway.jurisdiction == j)).scalars().all()
    return {"jurisdiction": j, "name": JUR_NAMES.get(j, j), "pathways": [pathway_view(p) for p in pws]}
