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
from array import array
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
        """`entries` maps each code to its names. Without `encode`, only keywords are used.

        Everything is held in numpy arrays, not Python objects: the ICD-10 index has 122,000
        names and about 5 million keyword postings, which as Python ints and dicts took over a
        gigabyte and most of the API's start-up time.
        """
        self.codes = list(entries)
        self.names: list[str] = []
        owner: list[int] = []  # code index of each name
        for c, names in enumerate(entries.values()):
            for name in dict.fromkeys(names):  # drop duplicates, keep order
                self.names.append(name)
                owner.append(c)
        self.owner = np.array(owner, dtype=np.int32)
        ids: dict[str, array[int]] = defaultdict(lambda: array("i"))
        tfs: dict[str, array[int]] = defaultdict(lambda: array("H"))
        lengths = np.zeros(len(self.names), dtype=np.float32)
        for i, name in enumerate(self.names):
            grams = Counter(trigrams(name))
            lengths[i] = sum(grams.values())
            for g, tf in grams.items():
                ids[g].append(i)
                tfs[g].append(tf)
        n = len(self.names)
        self.postings = {
            g: (np.frombuffer(ids[g], dtype=np.int32), np.frombuffer(tfs[g], dtype=np.uint16))
            for g in ids
        }
        self.idf = {
            g: math.log(1 + (n - len(p[0]) + 0.5) / (len(p[0]) + 0.5))
            for g, p in self.postings.items()
        }
        # BM25's length normalisation, per name, computed once.
        self.norm = (_K1 * (1 - _B + _B * lengths / lengths.mean())).astype(np.float32)
        self.encode = encode
        self.vectors = encode(self.names, "passage").astype(np.float16) if encode else None

    def _best_per_code(
        self, scores: npt.NDArray[np.float32], considered: npt.NDArray[np.intp]
    ) -> list[int]:
        best = np.full(len(self.codes), -np.inf, dtype=np.float32)
        np.maximum.at(best, self.owner[considered], scores[considered])
        ranked = np.nonzero(best > -np.inf)[0]
        order: list[int] = ranked[np.argsort(-best[ranked], kind="stable")].tolist()
        return order

    def keyword(self, query: str) -> list[int]:
        scores = np.zeros(len(self.names), dtype=np.float32)
        for g, qf in Counter(trigrams(query)).items():
            if g not in self.postings:
                continue
            ids, tf = self.postings[g]
            tf32 = tf.astype(np.float32)
            scores[ids] += qf * self.idf[g] * tf32 * (_K1 + 1) / (tf32 + self.norm[ids])
        return self._best_per_code(scores, np.nonzero(scores)[0])

    def semantic(self, query: str) -> list[int]:
        if self.encode is None or self.vectors is None:
            return []
        q = self.encode([query], "query")[0]
        # Multiply in float32 chunks: float16 storage halves memory, float32 keeps BLAS speed.
        similarity = np.concatenate(
            [chunk.astype(np.float32) @ q for chunk in np.array_split(self.vectors, 8)]
        )
        return self._best_per_code(similarity, np.arange(len(self.names)))

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
