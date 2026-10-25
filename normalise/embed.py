"""Multilingual sentence embeddings (intfloat/multilingual-e5-small), run with onnxruntime.

Texts become 384-number vectors where similar meanings sit close together, in any of ~100
languages: 'Kaliémie' lands near 'Potassium [Moles/volume] in Serum or Plasma'. E5 was trained
with 'query: ' and 'passage: ' prefixes, so the side of the search must be stated.
"""

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

MODEL = "intfloat/multilingual-e5-small"
# A fixed version: an update upstream would change every vector, silently stale the embedding
# caches, and could break the deployed image, which loads this exact snapshot offline.
REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
_BATCH = 64
_MAX_TOKENS = 64  # code names are short; truncating keeps batches fast


class Embedder:
    def __init__(self, model: str = MODEL, revision: str = REVISION) -> None:
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        self.tokenizer = Tokenizer.from_file(
            hf_hub_download(model, "onnx/tokenizer.json", revision=revision)
        )
        self.tokenizer.enable_truncation(_MAX_TOKENS)
        self.tokenizer.enable_padding()
        self.session = ort.InferenceSession(
            hf_hub_download(model, "onnx/model.onnx", revision=revision)
        )
        self.inputs = {i.name for i in self.session.get_inputs()}

    def encode(self, texts: Sequence[str], kind: str = "passage") -> npt.NDArray[np.float32]:
        """Unit-length vectors, one per text, so a dot product is the cosine similarity."""
        out = []
        for i in range(0, len(texts), _BATCH):
            batch = self.tokenizer.encode_batch([f"{kind}: {t}" for t in texts[i : i + _BATCH]])
            ids = np.array([e.ids for e in batch], dtype=np.int64)
            mask = np.array([e.attention_mask for e in batch], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self.inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            hidden = self.session.run(None, feed)[0]
            # Mean of the token vectors, ignoring padding.
            summed = (hidden * mask[..., None]).sum(axis=1)
            vectors = summed / mask.sum(axis=1, keepdims=True)
            out.append(vectors / np.linalg.norm(vectors, axis=1, keepdims=True))
        return np.concatenate(out).astype(np.float32)
