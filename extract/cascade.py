"""The extraction cascade the API runs: local NER first, the LLM only when the validator objects.

On the 500-document evaluation sample this matches Gemini's F1 (0.956) while sending a third of
documents to it, and gets more documents fully right than either extractor alone (62.2%).
Without an LLM (the Free tier, or no key configured) the NER result is returned with its issues
for the reviewer.
"""

import time
from dataclasses import dataclass, field
from typing import Literal

from extract.doctype import DocType, detect_doc_type
from extract.llm import GeminiExtractor, QuotaExhausted
from extract.ner import NerExtractor
from extract.schema import Extraction
from extract.validate import Issue, validate


@dataclass
class CascadeResult:
    doc_type: DocType
    extraction: Extraction
    source: Literal["ner", "llm"]
    issues: list[Issue]  # what the reviewer should check
    seconds: float
    notes: list[str] = field(default_factory=list)


class Cascade:
    def __init__(self, ner: NerExtractor, llm: GeminiExtractor | None = None) -> None:
        self.ner = ner
        self.llm = llm

    def run(self, doc_id: str, text: str) -> CascadeResult:
        start = time.perf_counter()
        doc_type = detect_doc_type(text)
        extraction = self.ner.extract(text)
        issues = validate(extraction, doc_type)
        source: Literal["ner", "llm"] = "ner"
        notes: list[str] = []
        if issues and self.llm is None:
            notes.append("LLM fallback off: issues are left for review")
        elif issues and self.llm is not None:
            try:
                llm = self.llm.extract(doc_id, text, doc_type)
            except QuotaExhausted:
                notes.append("LLM quota exhausted: issues are left for review")
            else:
                llm_issues = validate(llm.extraction, doc_type)
                # Keep whichever answer the validator finds fewer problems with; on a tie the
                # LLM, which corrects OCR damage the local model can only copy.
                if llm.valid and len(llm_issues) <= len(issues):
                    extraction, issues, source = llm.extraction, llm_issues, "llm"
        return CascadeResult(
            doc_type, extraction, source, issues, time.perf_counter() - start, notes
        )
