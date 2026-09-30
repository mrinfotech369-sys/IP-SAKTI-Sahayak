"""Language, intent, jurisdiction and safety detection for user queries."""
import re
from dataclasses import dataclass, field

DEVANAGARI = re.compile(r"[ऀ-ॿ]")

INTENTS = [
    "GENERAL_INFORMATION",
    "INNOVATION_ANALYSIS",
    "PATENT_SEARCH",
    "PRIOR_ART_SEARCH",
    "SCIENTIFIC_EVIDENCE",
    "TRADITIONAL_KNOWLEDGE",
    "REGULATORY",
    "JURISDICTION_COMPARISON",
    "PRODUCT_CLASSIFICATION",
    "CITATION_VERIFICATION",
    "DOCUMENT_EXPLANATION",
    "EVIDENCE_GAP",
    "REPORT_GENERATION",
]

_INTENT_KEYWORDS: dict[str, list[str]] = {
    "PRIOR_ART_SEARCH": ["prior art", "prior-art", "novelty", "anticipat", "find patents", "similar patents", "existing patents", "पूर्व कला"],
    "PATENT_SEARCH": ["patent", "3(p)", "3 (p)", "patentab", "invention", "inventive step", "पेटेंट"],
    "SCIENTIFIC_EVIDENCE": ["study", "studies", "clinical", "trial", "efficacy", "pubmed", "bioavailability", "pharmacokinetic", "अध्ययन", "शोध"],
    "TRADITIONAL_KNOWLEDGE": ["traditional knowledge", "tkdl", "classical text", "benefit sharing", "benefit-sharing", "biodiversity", " nba", " abs ", "पारंपरिक ज्ञान", "जैव विविधता"],
    "JURISDICTION_COMPARISON": ["compare", "comparison", "versus", " vs ", "difference between", "तुलना"],
    "PRODUCT_CLASSIFICATION": ["classif", "category", "categor", "what kind of product", "which pathway", "श्रेणी", "वर्गीकरण"],
    "REGULATORY": ["regulat", "licen", "approval", "approve", "fda", "tga", "cdsco", "fssai", "ayush", "rule 158", "dshea", "label", "listed medicine",
                   "disclaimer", "structure/function", "cfr", " asu", "p&p", "proprietary", "supplement", "register", "notification", "gmp",
                   "नियामक", "लाइसेंस", "नियम"],
    "CITATION_VERIFICATION": ["verify", "is it true", "citation", "does the source", "सत्यापित"],
    "EVIDENCE_GAP": ["gap", "missing evidence", "what is missing", "कमी"],
    "REPORT_GENERATION": ["report", "export", "रिपोर्ट"],
    "INNOVATION_ANALYSIS": ["my innovation", "my formulation", "this innovation", "this formulation", "मेरा उत्पाद"],
    "DOCUMENT_EXPLANATION": ["explain section", "what does section", "explain rule", "meaning of", "define", "definition", "परिभाषा", "समझाइए"],
}
# Tie-break priority when two intents score equally.
_PRIORITY = ["PRIOR_ART_SEARCH", "JURISDICTION_COMPARISON", "PRODUCT_CLASSIFICATION", "TRADITIONAL_KNOWLEDGE", "REGULATORY",
             "SCIENTIFIC_EVIDENCE", "PATENT_SEARCH", "CITATION_VERIFICATION", "EVIDENCE_GAP", "DOCUMENT_EXPLANATION",
             "INNOVATION_ANALYSIS", "REPORT_GENERATION"]

UNSUPPORTED_JURISDICTIONS = r"\b(brazil\w*|anvisa|european union|\beu\b|ema|china|chinese|nmpa|canada|canadian|health canada|united kingdom|\buk\b|mhra|japan\w*|pmda|germany|singapore|hsa|malaysia|nigeria|south africa|russia\w*)\b"

_JURISDICTION_PATTERNS = {
    "IN": r"\b(india|indian|ayush|cdsco|fssai|ip india|nba|national biodiversity|drugs and cosmetics|patents act|biological diversity act|rule 158b?)\b|भारत|आयुष",
    "US": r"\b(usa|u\.s\.|united states|america|american|fda|dshea|cfr|uspto)\b|अमेरिका",
    "AU": r"\b(australia|australian|tga|artg|therapeutic goods)\b|ऑस्ट्रेलिया",
}

MEDICAL_PATTERNS = [
    r"\b(will|can|does|do|would|could)\b[^?.]{0,60}\b(cure|cures|heal|heals|treat|treats|fix|reverse)\b",
    r"\bmy (anxiety|diabetes|disease|condition|pain|illness|disorder|blood pressure)\b",
    r"\b(should i take|how much should i take|dosage for me|dose for me|safe for me|prescribe me|diagnose)\b",
    r"इलाज|ठीक कर|दवा लेनी|खुराक कितनी",
]
LEGAL_CERTAINTY_PATTERNS = [
    r"\b(is|will) (my|this|our) (invention|product|formulation) (be )?(patentable|approved|granted)",
    r"\bfreedom to operate\b",
    r"\b(guarantee|guaranteed|definitely|certain(ly)?)\b.*\b(patent|approv|clear|infring)",
    r"\bwill (the )?(fda|tga|cdsco|regulator|patent office) approve",
    r"\bnon-?infringement\b",
    r"क्या .*पेटेंट मिलेगा|मंजूरी मिलेगी",
]
RESTRICTED_TK_PATTERNS = [
    r"tkdl.*\b(full|dump|download|all records|extract|scrape|give me|show me|access|entries|database)\b",
    r"\b(full|dump|download|scrape|bypass).*tkdl",
]
INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) instructions",
    r"(reveal|print|show) (your|the) (system )?prompt",
    r"you are now (dan|in developer mode)",
    r"disregard (the )?(rules|instructions)",
    r"execute (this|the following) command",
    r"send (the )?(secret|api key|credentials)",
]


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def detect_language(text: str) -> str:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "en"
    dev = sum(1 for c in letters if DEVANAGARI.match(c))
    return "hi" if dev / len(letters) > 0.3 else "en"


def detect_jurisdictions(text: str) -> list[str]:
    return [j for j, p in _JURISDICTION_PATTERNS.items() if re.search(p, text, re.I)]


def detect_injection(text: str) -> bool:
    return _any(INJECTION_PATTERNS, text)


@dataclass
class QueryAnalysis:
    language: str
    intent: str
    secondary_intents: list[str]
    jurisdictions: list[str]
    jurisdiction_label: str  # India | USA | Australia | Multiple | Unknown
    medical_request: bool
    legal_certainty_request: bool
    restricted_tk_request: bool
    injection_attempt: bool
    needs_jurisdiction: bool
    unsupported_jurisdictions: list[str]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


_LABELS = {"IN": "India", "US": "USA", "AU": "Australia"}


def analyze_query(text: str, *, selected_jurisdiction: str | None = None, mode: str | None = None, has_innovation: bool = False) -> QueryAnalysis:
    t = f" {text.lower()} "
    scores: dict[str, int] = {}
    for intent, kws in _INTENT_KEYWORDS.items():
        s = sum(1 for k in kws if k in t)
        if s:
            scores[intent] = s
    mode_intent = {
        "PATENT": "PRIOR_ART_SEARCH",
        "SCIENTIFIC": "SCIENTIFIC_EVIDENCE",
        "REGULATORY": "REGULATORY",
        "CROSS_JURISDICTION": "JURISDICTION_COMPARISON",
        "INNOVATION": "INNOVATION_ANALYSIS",
    }.get((mode or "").upper())
    ranked = sorted(scores, key=lambda k: (-scores[k], _PRIORITY.index(k) if k in _PRIORITY else 99))
    if mode_intent and mode_intent not in ranked:
        ranked.insert(0, mode_intent)
    if not ranked:
        ranked = ["INNOVATION_ANALYSIS" if has_innovation else "GENERAL_INFORMATION"]
    intent = ranked[0]

    jurs = detect_jurisdictions(text)
    if selected_jurisdiction and selected_jurisdiction.upper() in _LABELS and selected_jurisdiction.upper() not in jurs:
        jurs = jurs or [selected_jurisdiction.upper()]
    if intent == "JURISDICTION_COMPARISON" and len(jurs) < 2:
        jurs = sorted(set(jurs) | {"IN", "US", "AU"}, key=["IN", "US", "AU"].index)
    label = "Unknown" if not jurs else ("Multiple" if len(jurs) > 1 else _LABELS[jurs[0]])

    unsupported = sorted({m.group(0) for m in re.finditer(UNSUPPORTED_JURISDICTIONS, text, re.I)})
    regulatory = intent in ("REGULATORY", "PRODUCT_CLASSIFICATION") or "REGULATORY" in ranked[:2]
    return QueryAnalysis(
        language=detect_language(text),
        intent=intent,
        secondary_intents=ranked[1:4],
        jurisdictions=jurs,
        jurisdiction_label=label,
        medical_request=_any(MEDICAL_PATTERNS, text) and not re.search(r"\bclaim", text, re.I),
        legal_certainty_request=_any(LEGAL_CERTAINTY_PATTERNS, text),
        restricted_tk_request=_any(RESTRICTED_TK_PATTERNS, text),
        injection_attempt=detect_injection(text),
        needs_jurisdiction=regulatory and not jurs and not unsupported,
        unsupported_jurisdictions=unsupported,
    )
