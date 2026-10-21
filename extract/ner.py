"""NER extractor: a fine-tuned token classifier, run over overlapping windows.

The model call is passed in, so the same code runs the PyTorch model during training (to score
the dev set) and the int8 ONNX model at runtime. Where windows overlap, a token's logits are
averaged across them before choosing its tag.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from extract.ner_data import decode, to_extraction, windows
from extract.schema import Extraction

# (input_ids, attention_mask), each [windows, tokens] -> logits [windows, tokens, labels]
RunModel = Callable[[npt.NDArray[np.int64], npt.NDArray[np.int64]], npt.NDArray[np.float32]]


class NerExtractor:
    def __init__(self, tokenizer: Any, run: RunModel) -> None:
        self.tokenizer = tokenizer
        self.run = run

    def batch(self, text: str) -> tuple[Any, npt.NDArray[np.int64], npt.NDArray[np.int64]]:
        """The document's windows, padded to one width: (encoding, input ids, attention mask)."""
        enc = windows(self.tokenizer, text)
        width = max(len(ids) for ids in enc["input_ids"])
        pad = self.tokenizer.pad_token_id
        ids = np.array([i + [pad] * (width - len(i)) for i in enc["input_ids"]], dtype=np.int64)
        mask = np.array([m + [0] * (width - len(m)) for m in enc["attention_mask"]], dtype=np.int64)
        return enc, ids, mask

    def spans(self, text: str) -> list[tuple[str, int, int]]:
        enc, ids, mask = self.batch(text)
        logits = self.run(ids, mask)
        summed: dict[tuple[int, int], npt.NDArray[np.float32]] = {}
        for w, offsets in enumerate(enc["offset_mapping"]):
            for t, (start, end) in enumerate(offsets):
                if start < end:
                    key = (start, end)
                    summed[key] = summed[key] + logits[w, t] if key in summed else logits[w, t]
        keys = sorted(summed)
        # Summing, then taking the largest, picks the same tag as averaging would.
        return decode(keys, [int(np.argmax(summed[k])) for k in keys])

    def extract(self, text: str) -> Extraction:
        return to_extraction(text, self.spans(text))

    @classmethod
    def from_onnx(cls, model_dir: Path, model_file: str = "model.int8.onnx") -> "NerExtractor":
        import onnxruntime as ort
        from transformers import AutoTokenizer

        options = ort.SessionOptions()
        options.intra_op_num_threads = 1  # callers parallelise across documents
        session = ort.InferenceSession(str(model_dir / model_file), options)

        def run(ids: npt.NDArray[np.int64], mask: npt.NDArray[np.int64]) -> npt.NDArray[np.float32]:
            out = session.run(["logits"], {"input_ids": ids, "attention_mask": mask})
            return np.asarray(out[0], dtype=np.float32)

        return cls(AutoTokenizer.from_pretrained(model_dir), run)
