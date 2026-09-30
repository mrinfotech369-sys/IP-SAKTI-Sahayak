"""Innovation profiler: wizard input → structured profile + technical features.

Rule-based extraction only uses what the user entered. When an LLM is
configured, it may add candidate features from free text; those are always
marked `needs_confirmation` and never overwrite user-provided values.
"""
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.orm import FeatureType, Innovation, InnovationFeature, InnovationProfile, InnovationStatus
from app.services.llm import LLMError, get_llm
from app.services.terminology import TerminologyEngine

ORAL_FORMS = ("tablet", "capsule", "granule", "powder", "syrup", "churna", "vati", "kashaya", "decoction", "effervescent", "gummy", "drink", "liquid", "strip", "sachet")
TOPICAL_FORMS = ("cream", "oil", "taila", "ointment", "gel", "lotion", "lepa")
DISEASE_WORDS = re.compile(
    r"\b(treat|treats|treatment|cure|cures|prevent|prevents|mitigat\w*|disease|disorder|diabetes|cancer|hypertension|arthritis|depression|anxiety disorder|infection|covid)\b",
    re.I,
)
PROCESS_PHRASES = re.compile(
    r"(enzyme[- ]assisted \w+|supercritical \w+|spray[- ]dr\w+|freeze[- ]dr\w+|phospholipid complex\w*|nano\w*|liposom\w+|microencapsul\w+|"
    r"effervescent \w+|ultrasound[- ]assisted \w+|hydro[- ]alcoholic extract\w*|aqueous extract\w*|fermentation|standardi[sz]ed to [\w%. ]+)",
    re.I,
)


def _s(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def infer_route(dosage_form: str) -> tuple[str | None, str | None]:
    d = dosage_form.lower()
    if any(k in d for k in ORAL_FORMS):
        return "Oral", f"Route inferred as oral from dosage form '{dosage_form}'."
    if any(k in d for k in TOPICAL_FORMS):
        return "Topical", f"Route inferred as topical from dosage form '{dosage_form}'."
    return None, None


def build_profile(db: Session, inn: Innovation, wizard: dict, use_llm: bool = True) -> InnovationProfile:
    basic = wizard.get("basic", {})
    formulation = wizard.get("formulation", {})
    process = wizard.get("process", {})
    raw_ingredients = wizard.get("ingredients", []) or []
    claims = [c.strip() for c in (wizard.get("claims") or []) if c and c.strip()]
    markets = [m for m in (wizard.get("markets") or []) if m in ("IN", "US", "AU")]

    engine = TerminologyEngine(db)
    ingredients, botanicals, chemicals, terminology = [], [], [], []
    missing, ambiguities, assumptions = [], [], []

    for ing in raw_ingredients:
        name = _s(ing.get("common_name")) or _s(ing.get("sanskrit_name")) or _s(ing.get("botanical_name"))
        if not name:
            continue
        probe = " ".join(_s(ing.get(k)) for k in ("common_name", "sanskrit_name", "hindi_name", "botanical_name"))
        matches = engine.normalize(probe)
        match = matches[0] if matches else None
        user_bot = _s(ing.get("botanical_name"))
        entry = {
            "name": name,
            "sanskrit_name": _s(ing.get("sanskrit_name")) or None,
            "hindi_name": _s(ing.get("hindi_name")) or None,
            "botanical_name": user_bot or None,
            "chemical_name": _s(ing.get("chemical_name")) or None,
            "extract": _s(ing.get("extract")) or None,
            "quantity": _s(ing.get("quantity")) or None,
            "source": _s(ing.get("source")) or None,
            "normalized": None,
            "status": "USER_PROVIDED",
        }
        if match:
            terminology.append(match.to_dict())
            if match.ambiguous:
                entry["status"] = "NEEDS_CONFIRMATION"
                if not user_bot:
                    ambiguities.append(
                        f"'{name}': {match.ambiguity_note} Candidates: {', '.join(match.candidate_species)}."
                    )
            elif match.botanical:
                entry["normalized"] = match.botanical
                if user_bot and user_bot.lower() != match.botanical.lower():
                    ambiguities.append(
                        f"'{name}': user botanical name '{user_bot}' differs from curated '{match.botanical}'. Confirm species."
                    )
                    entry["status"] = "NEEDS_CONFIRMATION"
                elif not user_bot:
                    assumptions.append(f"'{name}' normalised to {match.botanical} via terminology engine — needs confirmation.")
                    entry["status"] = "NEEDS_CONFIRMATION"
            for c in match.chemical:
                if c not in chemicals:
                    chemicals.append(c)
        bot = user_bot or entry["normalized"]
        if bot:
            botanicals.append(bot)
        elif not (match and match.ambiguous):
            missing.append(f"Botanical name for '{name}' is not provided and could not be resolved.")
        if entry["chemical_name"] and entry["chemical_name"] not in chemicals:
            chemicals.append(entry["chemical_name"])
        if not entry["quantity"]:
            missing.append(f"Quantity/concentration for '{name}' is not specified.")
        if not entry["extract"]:
            missing.append(f"Plant part / extract type for '{name}' is not specified.")
        ingredients.append(entry)

    dosage_form = _s(formulation.get("dosage_form"))
    route = _s(formulation.get("route"))
    if not route and dosage_form:
        r, why = infer_route(dosage_form)
        if r:
            route = r
            assumptions.append(why)
    intended_use = _s(basic.get("intended_use"))
    extraction = _s(process.get("extraction"))
    process_text = "; ".join(x for x in (_s(process.get("processing")), _s(process.get("purification")), _s(process.get("novel_process")), _s(process.get("unique_parameters"))) if x)
    composition = "; ".join(x for x in (_s(formulation.get("composition")), _s(formulation.get("formulation"))) if x)
    manufacturing = _s(process.get("manufacturing"))

    for label, val in (
        ("Dosage form", dosage_form), ("Route of administration", route), ("Intended use", intended_use),
        ("Extraction method", extraction), ("Manufacturing location", manufacturing),
    ):
        if not val:
            missing.append(f"{label} is not specified.")
    if not markets:
        missing.append("Target market(s) are not selected; regulatory analysis cannot be jurisdiction-specific.")
    if not claims:
        missing.append("No proposed claims provided; claims drive regulatory classification.")
    if not ingredients:
        missing.append("No ingredients provided.")

    for c in claims:
        if DISEASE_WORDS.search(c):
            ambiguities.append(f"Proposed claim may be a disease/treatment claim: \"{c}\". This affects product category in every market.")

    # --- Features -----------------------------------------------------------
    features: list[dict] = []

    def feat(ftype: FeatureType, name: str, desc: str | None = None, norm: str | None = None, imp: float = 0.5, src: str = "USER_PROVIDED"):
        if name:
            features.append({"feature_type": ftype, "name": name[:300], "description": desc, "normalized_term": norm, "importance": imp, "source": src})

    for ing in ingredients:
        feat(FeatureType.INGREDIENT, ing["name"], ing.get("extract"), ing.get("botanical_name") or ing.get("normalized"), 0.8)
    if composition:
        feat(FeatureType.COMPOSITION, composition[:120], composition, None, 0.7)
    if extraction:
        feat(FeatureType.EXTRACTION, extraction[:120], extraction, None, 0.9)
    if process_text:
        feat(FeatureType.PROCESS, process_text[:120], process_text, None, 0.9 if process.get("novel_process") else 0.6)
    if formulation.get("delivery_mechanism"):
        feat(FeatureType.DELIVERY, _s(formulation["delivery_mechanism"])[:120], _s(formulation["delivery_mechanism"]), None, 0.8)
    if dosage_form:
        feat(FeatureType.DOSAGE_FORM, dosage_form, route or None, None, 0.6)
    for c in claims:
        feat(FeatureType.CLAIM, c[:120], c, None, 0.7)
    if intended_use:
        feat(FeatureType.USE, intended_use[:120], intended_use, None, 0.5)
    if manufacturing:
        feat(FeatureType.MANUFACTURING, manufacturing[:120], manufacturing, None, 0.3)

    free_text = " ".join([_s(basic.get("description")), extraction, process_text, composition, _s(formulation.get("delivery_mechanism")), _s(formulation.get("preparation_method"))])
    phrases = sorted({m.group(0).strip().lower() for m in PROCESS_PHRASES.finditer(free_text)})
    search_terms = []
    for x in [*(i["name"] for i in ingredients), *botanicals, *chemicals, *phrases, dosage_form]:
        if x and x not in search_terms:
            search_terms.append(x)

    method = "rules"
    llm = get_llm()
    if use_llm and llm.available and free_text.strip():
        try:
            out = llm.complete_json(
                "Extract technical features from an Ayurveda innovation description. Only use information explicitly "
                "present in the text; never invent. Return JSON {\"features\": [{\"type\": \"PROCESS|EXTRACTION|DELIVERY|"
                "COMPOSITION|DOSAGE_FORM|OTHER\", \"name\": \"...\", \"evidence_span\": \"exact quote\"}], \"ambiguities\": [\"...\"]}",
                free_text[:3000],
                max_tokens=600,
            )
            existing = {f["name"].lower() for f in features}
            for fx in (out.get("features") or [])[:8]:
                span = _s(fx.get("evidence_span"))
                name = _s(fx.get("name"))
                if not name or name.lower() in existing or (span and span.lower() not in free_text.lower()):
                    continue  # reject anything not grounded in the user's own text
                try:
                    ftype = FeatureType(_s(fx.get("type")).upper())
                except ValueError:
                    ftype = FeatureType.OTHER
                feat(ftype, name, f"Needs confirmation — AI-extracted from: \"{span}\"", None, 0.6, "AI_EXTRACTED")
            for amb in (out.get("ambiguities") or [])[:5]:
                ambiguities.append(f"Needs confirmation: {_s(amb)}")
            method = "rules+llm"
        except LLMError:
            method = "rules (LLM unavailable)"

    prof = inn.profile or InnovationProfile(innovation_id=inn.id)
    prof.ingredients = ingredients
    prof.botanical_names = botanicals
    prof.chemical_entities = chemicals
    prof.composition = composition or None
    prof.process = process_text or None
    prof.extraction_method = extraction or None
    prof.dosage_form = dosage_form or None
    prof.route = route or None
    prof.intended_use = intended_use or None
    prof.claims = claims
    prof.target_market = markets
    prof.manufacturing_location = manufacturing or None
    prof.structured_features = [{**f, "feature_type": f["feature_type"].value} for f in features]
    prof.search_terms = search_terms
    prof.terminology = terminology
    prof.assumptions = assumptions
    prof.missing_information = missing
    prof.ambiguities = ambiguities
    prof.extraction_method_used = method
    prof.user_confirmed = False
    if inn.profile is None:
        db.add(prof)
        inn.profile = prof

    inn.features.clear()
    db.flush()
    for f in features:
        inn.features.append(InnovationFeature(**f))
    inn.target_markets = markets
    if inn.status == InnovationStatus.DRAFT:
        inn.status = InnovationStatus.PROFILED
    db.flush()
    return prof


def apply_profile_edits(db: Session, inn: Innovation, edits: dict) -> InnovationProfile:
    """User edits to the extracted profile. Editing marks the profile as user-confirmed."""
    prof = inn.profile
    allowed = {
        "ingredients", "botanical_names", "chemical_entities", "composition", "process", "extraction_method",
        "dosage_form", "route", "intended_use", "claims", "target_market", "manufacturing_location",
        "assumptions", "missing_information", "ambiguities",
    }
    for k, v in edits.items():
        if k in allowed:
            setattr(prof, k, v)
    if "features" in edits:
        inn.features.clear()
        db.flush()
        for f in edits["features"]:
            inn.features.append(
                InnovationFeature(
                    feature_type=FeatureType(f.get("feature_type", "OTHER")),
                    name=f["name"][:300],
                    description=f.get("description"),
                    normalized_term=f.get("normalized_term"),
                    importance=float(f.get("importance", 0.5)),
                    source=f.get("source", "USER_PROVIDED"),
                )
            )
        prof.structured_features = [
            {"feature_type": f.feature_type.value, "name": f.name, "description": f.description,
             "normalized_term": f.normalized_term, "importance": f.importance, "source": f.source}
            for f in inn.features
        ]
    if "target_market" in edits:
        inn.target_markets = edits["target_market"]
    prof.user_confirmed = bool(edits.get("confirm", True))
    db.flush()
    return prof
