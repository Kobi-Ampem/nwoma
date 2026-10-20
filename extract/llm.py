"""LLM extractor: Gemini with structured output.

The model copies fields as printed and `normalise.fields` converts them, the same code the NER
model's output goes through. Every response is cached on disk, keyed by model, prompt and text,
so re-running an evaluation is free and a run stopped by the daily quota resumes where it ended.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from extract.schema import Extraction

PROMPT = """You extract data from a clinical laboratory report, in English or French.
The text may come from OCR of a scan, so it can contain misread characters and stray symbols.

Rules:
- Copy each field exactly as printed: keep the date format, decimal commas, flag words and
  name order. Do not translate, convert units or reformat.
- Only correct a character when OCR has obviously garbled it (e.g. 'Potassiurn' -> 'Potassium').
- One result entry per test row, in document order. Panel headings such as 'Biochemistry' are
  not tests.
- clinician is the requesting doctor, without the title (no 'Dr').
- Use null for a field that is not in the text. Never guess a value.

Report text:
"""
PROMPT_VERSION = hashlib.sha256(PROMPT.encode()).hexdigest()[:8]

_RETRIES = 5
# Normal calls take ~10 s. Without a timeout, one stalled connection hangs the run forever.
_TIMEOUT_MS = 60_000
_EMPTY = Extraction(
    patient_name=None, birth_date=None, sex=None, collection_date=None, clinician=None, results=[]
)


class QuotaExhausted(RuntimeError):
    """The daily quota is used up. Cached results are kept; re-run tomorrow to continue."""


@dataclass(frozen=True)
class LLMResult:
    extraction: Extraction
    input_tokens: int
    output_tokens: int  # includes thinking tokens, which are billed as output
    latency_s: float
    cached: bool
    valid: bool = True  # False: the reply did not fit the schema and counts as empty


class GeminiExtractor:
    def __init__(
        self,
        model: str,
        cache_dir: Path,
        client: genai.Client | None = None,
        min_interval_s: float = 0.0,
        thinking_level: str | None = None,
    ) -> None:
        self.model = model
        self.cache_dir = cache_dir / model / PROMPT_VERSION
        # Reads GEMINI_API_KEY.
        self.client = client or genai.Client(http_options=types.HttpOptions(timeout=_TIMEOUT_MS))
        self.min_interval_s = min_interval_s  # spaces calls to stay under requests per minute
        self.config = types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=Extraction,
            thinking_config=(
                types.ThinkingConfig(thinking_level=thinking_level)  # type: ignore[arg-type]
                if thinking_level
                else None
            ),
        )
        self._last_call = 0.0

    def extract(self, doc_id: str, text: str) -> LLMResult:
        key = hashlib.sha256(text.encode()).hexdigest()[:12]
        path = self.cache_dir / f"{doc_id}-{key}.json"
        if path.exists():
            saved = json.loads(path.read_text())
            return LLMResult(
                extraction=Extraction.model_validate(saved["extraction"]),
                input_tokens=saved["input_tokens"],
                output_tokens=saved["output_tokens"],
                latency_s=saved["latency_s"],
                cached=True,
                valid=saved["valid"],
            )
        result = self._call(text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "extraction": result.extraction.model_dump(),
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "latency_s": result.latency_s,
                    "valid": result.valid,
                },
                ensure_ascii=False,
            )
        )
        return result

    def _call(self, text: str) -> LLMResult:
        for attempt in range(_RETRIES):
            wait = self.min_interval_s - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            start = time.perf_counter()
            try:
                response = self.client.models.generate_content(
                    model=self.model, contents=PROMPT + text, config=self.config
                )
            except errors.APIError as e:
                if e.code == 429 and "day" in str(e).lower():
                    raise QuotaExhausted(str(e)) from e
                if e.code in (429, 500, 503) and attempt < _RETRIES - 1:
                    time.sleep(2 ** (attempt + 2))  # 4, 8, 16, 32 s: give the service room
                    continue
                raise
            except httpx.TransportError:  # timed out or the connection dropped
                if attempt < _RETRIES - 1:
                    time.sleep(2 ** (attempt + 2))
                    continue
                raise
            latency = time.perf_counter() - start
            usage = response.usage_metadata
            try:
                extraction, valid = Extraction.model_validate_json(response.text or ""), True
            except ValidationError:
                extraction, valid = _EMPTY, False
            return LLMResult(
                extraction=extraction,
                input_tokens=(usage.prompt_token_count or 0) if usage else 0,
                output_tokens=(
                    (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
                    if usage
                    else 0
                ),
                latency_s=latency,
                cached=False,
                valid=valid,
            )
        raise RuntimeError("unreachable")
