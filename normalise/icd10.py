"""Map a diagnosis as written in a letter (English or French) to an ICD-10-CM code.

Search space: every billable code in the CMS ICD-10-CM file (~75,000), indexed by its short and
long descriptions. French has no official CIM-10 names here (their reuse terms are unclear), so
French diagnoses reach the English descriptions through the multilingual embeddings alone.
"""

from pathlib import Path

from normalise.loinc import _cached
from normalise.retrieval import Encode, Hit, HybridIndex, fold


def load_icd10(order_file: Path) -> dict[str, list[str]]:
    """Billable codes with a dot (E11.9), each with its short and long description."""
    entries: dict[str, list[str]] = {}
    with order_file.open(encoding="utf-8") as f:
        for line in f:
            if line[14] != "1":  # header rows are categories, not codes a record can use
                continue
            raw = line[6:13].strip()
            code = raw if len(raw) <= 3 else f"{raw[:3]}.{raw[3:]}"
            entries[code] = [line[16:76].strip(), line[77:].strip()]
    return entries


_DEPTH = 50
# Words that, if written, justify a more specific code than the default.
_TYPE1 = ("type 1", "type i ", "insulin-dependent", "insulinodependant")
_PREGNANCY = ("pregnan", "grossesse", "gestation", "obstetric", "postpartum")
_NEWBORN = ("newborn", "neonat", "nouveau-ne", "perinatal")
_OTHER_DIABETES = ("drug", "chemical", "secondary", "underlying condition", "medicament")


class Icd10Mapper:
    def __init__(self, order_file: Path, encode: Encode | None = None, cache: Path | None = None):
        entries = load_icd10(order_file)
        self.descriptions = {code: names[-1] for code, names in entries.items()}
        if encode is not None and cache is not None:
            encode = _cached(encode, entries, cache)
        self.index = HybridIndex(entries, encode)

    def map(self, diagnosis: str, k: int = 5, guidelines: bool = True) -> list[Hit]:
        """Top-k codes. With `guidelines`, two ICD-10-CM coding rules rerank the candidates
        (fixed rules, not tuned weights):

        - Code only what is documented: when the letter gives no detail, prefer the
          'unspecified' or 'without complications' code, and among the rest the less detailed.
        - Diabetes of unstated type is coded as type 2, E11 (guideline I.C.4.a.2): type 1 (E10)
          and drug-, chemical- or condition-induced diabetes (E08, E09, E13) need it written.
        - Pregnancy (chapter 15, O codes) and perinatal (chapter 16, P codes) codes only when the
          letter mentions pregnancy or a newborn.
        """
        hits = self.index.search(diagnosis, k=_DEPTH if guidelines else k, depth=_DEPTH)
        if not guidelines:
            return hits
        text = fold(diagnosis)

        def key(h: Hit) -> tuple[bool, float]:
            desc = fold(self.descriptions[h.code])
            wrong_diabetes = (h.code.startswith("E10") and not any(w in text for w in _TYPE1)) or (
                h.code[:3] in {"E08", "E09", "E13"} and not any(w in text for w in _OTHER_DIABETES)
            )
            default = "unspecified" in desc or "without complications" in desc
            detail = len(h.code.replace(".", ""))  # more characters, more specific
            wrong_chapter = (h.code[0] == "O" and not any(w in text for w in _PREGNANCY)) or (
                h.code[0] == "P" and not any(w in text for w in _NEWBORN)
            )
            return wrong_diabetes or wrong_chapter, -h.score * (1 + default) / detail

        return sorted(hits, key=key)[:k]
