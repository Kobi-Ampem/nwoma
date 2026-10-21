from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from normalise.retrieval import HybridIndex, fold

ENTRIES = {
    "2823-3": ["Potassium [Moles/volume] in Serum or Plasma", "Potassium SerPl-sCnc", "K"],
    "2951-2": ["Sodium [Moles/volume] in Serum or Plasma", "Sodium SerPl-sCnc", "Na"],
    "718-7": ["Hemoglobin [Mass/volume] in Blood", "Hgb Bld-mCnc", "Hb"],
}


def test_fold_removes_case_and_accents() -> None:
    assert fold("  Hémoglobine  A1c ") == "hemoglobine a1c"


def test_keywords_survive_ocr_typos_and_abbreviations() -> None:
    index = HybridIndex(ENTRIES)
    assert index.search("Potassiurn")[0].code == "2823-3"
    assert index.search("Hgb")[0].code == "718-7"
    assert index.search("Hémoglobine")[0].code == "718-7"


def _fake_encode(texts: Sequence[str], kind: str) -> npt.NDArray[np.float32]:
    """Meaning by hand: 'kaliemie' means potassium, which keywords cannot know."""
    topics = ["potassium", "sodium", "hemoglobin"]
    synonyms = {"kaliemie": "potassium", "natremie": "sodium"}
    vectors = []
    for t in texts:
        words = fold(t).replace("[", " ").split()
        hits = [synonyms.get(w, w) for w in words]
        vectors.append([float(any(h.startswith(topic) for h in hits)) + 1e-3 for topic in topics])
    v = np.array(vectors, dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_meaning_finds_what_keywords_cannot() -> None:
    keyword_only = HybridIndex(ENTRIES).search("Kaliémie")
    assert all(h.code != "2823-3" for h in keyword_only)  # no shared fragments: keywords fail
    hit = HybridIndex(ENTRIES, _fake_encode).search("Kaliémie")[0]
    assert hit.code == "2823-3" and hit.semantic_rank == 1


def test_fusion_reports_both_ranks() -> None:
    hit = HybridIndex(ENTRIES, _fake_encode).search("Potassium")[0]
    assert hit.code == "2823-3" and hit.keyword_rank == 1 and hit.semantic_rank == 1


def test_units_map_to_loinc_properties_whatever_the_micro_sign() -> None:
    from normalise.loinc import unit_properties

    # U+00B5 micro sign and U+03BC Greek mu look identical; both must work.
    assert unit_properties("µmol/L") == unit_properties("μmol/L") == {"SCnc"}
    assert unit_properties("10³/µL") == unit_properties("G/L") == {"NCnc"}
    assert unit_properties("g/L") == {"MCnc"}  # lower-case g is grams, not giga-cells
    assert unit_properties(None) == set()
