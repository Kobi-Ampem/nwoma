"""Hybrid retrieval: find the code whose names best match a query, by keywords and by meaning.

Each code has several names (official name, short name, synonyms, translations). Two searches run:

- BM25 over character 3-grams: rewards shared fragments, so abbreviations and OCR typos
  ('Potassiurn') still match, and rare fragments count more than common ones.
- Embeddings: cosine similarity of meaning vectors, so 'Kaliémie' finds 'Potassium' across
  languages.

Each search ranks codes by their best-matching name; reciprocal rank fusion (RRF) then adds
1 / (60 + rank) from each list. RRF uses ranks, not raw scores, so the two very different score
scales never need calibrating against each other.
"""

import math
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

Encode = Callable[[Sequence[str], str], npt.NDArray[np.float32]]
_K1, _B = 1.5, 0.75  # BM25's usual settings: term-frequency saturation and length normalisation
_RRF_K = 60  # the usual RRF constant: damps the gap between the very top ranks


def fold(text: str) -> str:
    """Lower case, no accents, single spaces: 'Hémoglobine  A1c' -> 'hemoglobine a1c'."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())


def trigrams(text: str) -> list[str]:
    padded = f" {fold(text)} "
    return [padded[i : i + 3] for i in range(len(padded) - 2)]


@dataclass(frozen=True)
class Hit:
    code: str
    score: float
    keyword_rank: int | None
    semantic_rank: int | None


class HybridIndex:
    def __init__(self, entries: dict[str, list[str]], encode: Encode | None = None) -> None:
        """`entries` maps each code to its names. Without `encode`, only keywords are used."""
        self.codes = list(entries)
        self.names: list[str] = []
        self.owner: list[int] = []  # code index of each name
        for c, names in enumerate(entries.values()):
            for name in dict.fromkeys(names):  # drop duplicates, keep order
                self.names.append(name)
                self.owner.append(c)
        self.grams = [Counter(trigrams(n)) for n in self.names]
        self.lengths = [sum(g.values()) for g in self.grams]
        self.avg_len = sum(self.lengths) / len(self.lengths)
        df: Counter[str] = Counter(g for grams in self.grams for g in grams)
        n = len(self.names)
        self.idf = {g: math.log(1 + (n - f + 0.5) / (f + 0.5)) for g, f in df.items()}
        self.postings: dict[str, list[int]] = defaultdict(list)
        for i, grams in enumerate(self.grams):
            for g in grams:
                self.postings[g].append(i)
        self.encode = encode
        self.vectors = encode(self.names, "passage") if encode else None

    def _best_per_code(self, name_scores: dict[int, float]) -> list[int]:
        best: dict[int, float] = {}
        for i, s in name_scores.items():
            c = self.owner[i]
            best[c] = max(best.get(c, -math.inf), s)
        return sorted(best, key=lambda c: -best[c])

    def keyword(self, query: str) -> list[int]:
        scores: dict[int, float] = defaultdict(float)
        for g, qf in Counter(trigrams(query)).items():
            for i in self.postings.get(g, ()):
                tf = self.grams[i][g]
                norm = tf + _K1 * (1 - _B + _B * self.lengths[i] / self.avg_len)
                scores[i] += qf * self.idf[g] * tf * (_K1 + 1) / norm
        return self._best_per_code(scores)

    def semantic(self, query: str) -> list[int]:
        if self.encode is None or self.vectors is None:
            return []
        similarity = self.vectors @ self.encode([query], "query")[0]
        return self._best_per_code(dict(enumerate(similarity.tolist())))

    def search(self, query: str, k: int = 5, depth: int = 50) -> list[Hit]:
        kw, sem = self.keyword(query)[:depth], self.semantic(query)[:depth]
        kw_rank = {c: r for r, c in enumerate(kw, 1)}
        sem_rank = {c: r for r, c in enumerate(sem, 1)}
        fused = {
            c: sum(1 / (_RRF_K + ranks[c]) for ranks in (kw_rank, sem_rank) if c in ranks)
            for c in kw_rank.keys() | sem_rank.keys()
        }
        top = sorted(fused, key=lambda c: -fused[c])[:k]
        return [Hit(self.codes[c], fused[c], kw_rank.get(c), sem_rank.get(c)) for c in top]
