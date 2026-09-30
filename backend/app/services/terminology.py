"""Terminology normalization across Sanskrit / Hindi / English / botanical / chemical names.

Common names are never silently mapped to one species: terms with an
`ambiguity_note` or several `candidate_species` are flagged for confirmation.
"""
import re
from dataclasses import asdict, dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.orm import Term


@dataclass
class TermMatch:
    original: str
    canonical: str
    domain: str
    english: Optional[str]
    sanskrit: Optional[str]
    hindi: Optional[str]
    botanical: Optional[str]
    chemical: list[str]
    alternatives: list[str]
    ambiguous: bool
    ambiguity_note: Optional[str]
    candidate_species: list[str] = field(default_factory=list)
    selected_meaning: Optional[str] = None
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def expansions(self) -> list[str]:
        vals = [self.canonical, self.english, self.sanskrit, self.botanical, *self.chemical, *self.alternatives]
        out, seen = [], set()
        for v in vals:
            if v and v.lower() not in seen:
                seen.add(v.lower())
                out.append(v)
        return out


class TerminologyEngine:
    def __init__(self, db: Session):
        self._terms = db.execute(select(Term)).scalars().all()
        self._index: list[tuple[re.Pattern, Term, str]] = []
        for t in self._terms:
            names = {t.canonical, t.english, t.sanskrit, t.hindi, t.botanical, *(t.aliases or [])}
            for n in sorted({x for x in names if x}, key=len, reverse=True):
                # Devanagari has no \b word boundaries in Python's re; match literally.
                if re.search(r"[ऀ-ॿ]", n):
                    pat = re.compile(re.escape(n))
                else:
                    pat = re.compile(r"(?<![\w])" + re.escape(n) + r"(?![\w])", re.I)
                self._index.append((pat, t, n))

    def normalize(self, text: str) -> list[TermMatch]:
        found: dict[str, TermMatch] = {}
        for pat, t, name in self._index:
            m = pat.search(text or "")
            if not m or t.id in found:
                continue
            ambiguous = bool(t.ambiguity_note) or len(t.candidate_species or []) > 1
            selected = None if ambiguous else (t.botanical or t.canonical)
            reason = (
                "Needs confirmation: common name maps to more than one candidate species."
                if ambiguous
                else f"Matched '{m.group(0)}' to the curated terminology entry for {t.canonical}."
            )
            found[t.id] = TermMatch(
                original=m.group(0),
                canonical=t.canonical,
                domain=t.domain,
                english=t.english,
                sanskrit=t.sanskrit,
                hindi=t.hindi,
                botanical=t.botanical,
                chemical=list(t.chemical or []),
                alternatives=list(t.aliases or []),
                ambiguous=ambiguous,
                ambiguity_note=t.ambiguity_note,
                candidate_species=list(t.candidate_species or []),
                selected_meaning=selected,
                reason=reason,
            )
        return list(found.values())

    @staticmethod
    def expand(matches: list[TermMatch]) -> list[str]:
        out: list[str] = []
        for m in matches:
            for e in m.expansions():
                if e not in out:
                    out.append(e)
        return out
