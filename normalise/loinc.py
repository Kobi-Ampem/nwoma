"""Map a printed lab test name (and its unit) to a LOINC code.

Search space: LOINC's 2,000 most common lab results, plus every other active quantitative lab
code for the same component and specimen. The ranking is built from US usage, where mg/dL
dominates, so the SI-unit codes European and African labs report (creatinine in µmol/L ranks
2,641; urea in mmol/L is unranked) would otherwise be missing.

Names come from the official table only: long and short names, display name, synonyms, and the
French linguistic variant. Never from the generator's catalogue, which would be the answer key.

A LOINC code includes the property measured, so the printed unit decides between codes the names
cannot: 'Créatinine' in µmol/L is 14682-9 (moles), in mg/dL it is 2160-0 (mass).
"""

import csv
import hashlib
import math
import unicodedata
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import numpy.typing as npt

from normalise.retrieval import Encode, Hit, HybridIndex, fold

_TOP = 2000
_DEPTH = 200  # candidates per search; LOINC has dozens of near-identical codes per test
PRIOR = 4.0  # weight of the popularity prior, chosen on the dev split (top-1 60.7%, top-5 82.5%)
_URINE = {"Urine"}
_BLOOD = {"Ser/Plas", "Bld", "Ser", "Plas", "BldV", "BldA", "RBC"}
_GENERIC_SYNONYM = 50  # a synonym shared by more codes than this ('Serum', 'Level') says nothing

# Printed unit -> LOINC properties it can measure.
_UNIT_PROPERTY: dict[str, set[str]] = {
    "MCnc": {"g/dl", "mg/dl", "g/l", "mg/l", "µg/l", "ng/ml"},
    "SCnc": {"mmol/l", "µmol/l", "umol/l", "nmol/l"},
    "NCnc": {"10⁶/µl", "10³/µl", "10^6/ul", "10^3/ul", "t/l", "g/l (count)", "/µl"},
    "CCnc": {"u/l", "ui/l", "iu/l"},
    "EntMeanVol": {"fl"},
    "EntMass": {"pg"},
    "VFr": {"%"},
    "MFr": {"%"},
    "MRto": {"mg/g", "mg/mmol"},
    "ArVRat": {"ml/min/1.73m²", "ml/min/1,73m²", "ml/min/1.73m2"},
}
# French counts print G/L and T/L, which collide with mass g/L: blood counts are told apart
# by these exact spellings (upper case G and T).
_COUNT_UNITS = {"G/L", "T/L"}


def unit_properties(unit: str | None) -> set[str]:
    if not unit:
        return set()
    if unit.strip() in _COUNT_UNITS:
        return {"NCnc"}
    u = _norm_unit(unit)
    return {prop for prop, units in _UNIT_PROPERTY.items() if u in {_norm_unit(x) for x in units}}


def _norm_unit(unit: str) -> str:
    """One spelling per unit. NFKC folds look-alikes ('10³' -> '103'); casefold() then turns
    the micro sign (U+00B5) into Greek mu (U+03BC). Both sides of a comparison go through here,
    so the table and the input cannot drift apart."""
    return unicodedata.normalize("NFKC", unit).casefold().replace(" ", "")


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_entries(loinc_dir: Path) -> tuple[dict[str, list[str]], dict[str, dict[str, str]]]:
    """Names per code in the search space, and each code's LOINC table row."""
    table = _read(loinc_dir / "LoincTable" / "Loinc.csv")
    rank = {r["LOINC_NUM"]: int(r["COMMON_TEST_RANK"] or 0) for r in table}
    top = [r for r in table if 0 < rank[r["LOINC_NUM"]] <= _TOP]
    common = {(r["COMPONENT"], r["SYSTEM"]) for r in top}
    space = {
        r["LOINC_NUM"]: r
        for r in table
        if (0 < rank[r["LOINC_NUM"]] <= _TOP)
        or (
            (r["COMPONENT"], r["SYSTEM"]) in common
            and r["CLASSTYPE"] == "1"  # laboratory
            and r["STATUS"] == "ACTIVE"
            and r["SCALE_TYP"] == "Qn"  # a number, as on our reports
        )
    }
    french = {
        r["LOINC_NUM"]: r
        for r in _read(
            next((loinc_dir / "AccessoryFiles" / "LinguisticVariants").glob("frFR*.csv"))
        )
        if r["LOINC_NUM"] in space
    }

    def synonyms(row: dict[str, str] | None) -> list[str]:
        return [s.strip() for s in (row or {}).get("RELATEDNAMES2", "").split(";") if s.strip()]

    spread = Counter(
        fold(s) for code in space for s in synonyms(space[code]) + synonyms(french.get(code))
    )
    entries: dict[str, list[str]] = {}
    for code, row in space.items():
        fr = french.get(code, {})
        names = [
            row["LONG_COMMON_NAME"],
            row["SHORTNAME"],
            row["DisplayName"],
            row["COMPONENT"],
            fr.get("LONG_COMMON_NAME", ""),
            fr.get("SHORTNAME", ""),
            fr.get("LinguisticVariantDisplayName", ""),
            fr.get("COMPONENT", ""),
        ]
        names += [s for s in synonyms(row) + synonyms(fr) if spread[fold(s)] <= _GENERIC_SYNONYM]
        entries[code] = [n for n in names if n]
    return entries, {code: space[code] for code in entries}


class LoincMapper:
    def __init__(
        self, loinc_dir: Path, encode: Encode | None = None, cache: Path | None = None
    ) -> None:
        entries, self.rows = load_entries(loinc_dir)
        if encode is not None and cache is not None:
            encode = _cached(encode, entries, cache)
        self.index = HybridIndex(entries, encode)

    def popularity(self, code: str) -> float:
        """1 for LOINC's most common test, falling to 0 at rank 30,000; 0 if unranked."""
        rank = int(self.rows[code]["COMMON_TEST_RANK"] or 0)
        return 0.0 if rank <= 0 else 1 - math.log(rank) / math.log(30_000)

    def map(
        self,
        name: str,
        unit: str | None = None,
        k: int = 5,
        use_unit: bool = True,
        prior: float = PRIOR,
    ) -> list[Hit]:
        """Top-k codes for a printed name and unit.

        Hard preferences first: a property that fits the unit, then the specimen the name
        implies (urine if it says so, otherwise serum, plasma or blood). Within those, relevance
        times (1 + prior x popularity): a common code wins among near-ties, but popularity
        multiplies relevance, so an irrelevant code cannot win just by being common.
        """
        hits = self.index.search(name, k=_DEPTH, depth=_DEPTH)
        wanted = unit_properties(unit) if use_unit else set()
        specimen = _URINE if "urin" in fold(name) else _BLOOD

        def key(h: Hit) -> tuple[bool, bool, float]:
            row = self.rows[h.code]
            return (
                bool(wanted) and row["PROPERTY"] not in wanted,
                use_unit and row["SYSTEM"] not in specimen,
                -h.score * (1 + prior * self.popularity(h.code)),
            )

        return sorted(hits, key=key)[:k]


def _cached(encode: Encode, entries: dict[str, list[str]], cache: Path) -> Encode:
    """Embedding thousands of names takes a minute or two; reuse them while the names are
    unchanged. Queries are always encoded fresh."""
    names = list(dict.fromkeys(n for ns in entries.values() for n in ns))
    key = hashlib.sha256("\n".join(names).encode()).hexdigest()[:12]
    path = cache.with_name(f"{cache.stem}-{key}.npy")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, encode(names, "passage"))
    saved = dict(zip(names, np.load(path), strict=True))

    def encode_with_cache(texts: Sequence[str], kind: str) -> npt.NDArray[np.float32]:
        if kind == "passage" and all(t in saved for t in texts):
            return np.stack([saved[t] for t in texts])
        return encode(texts, kind)

    return encode_with_cache
