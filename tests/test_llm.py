"""The Gemini extractor with a fake client: offline, free and deterministic."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import errors

from extract.llm import GeminiExtractor, QuotaExhausted

_REPLY = (
    '{"patient_name": "Anne Chauvin", "birth_date": "30/06/1963", "sex": "F", '
    '"collection_date": "27/04/2025", "clinician": "Constance Delattre", "results": '
    '[{"test_name": "Hémoglobine", "value": "12,7", "unit": "g/dL", '
    '"ref_range": "12,0 - 17,5", "flag": null}]}'
)


class _FakeModels:
    def __init__(self, replies: list[Any]) -> None:
        self.replies = replies
        self.calls = 0

    def generate_content(self, **_: Any) -> Any:
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        if isinstance(reply, Exception):
            raise reply
        usage = SimpleNamespace(
            prompt_token_count=500, candidates_token_count=80, thoughts_token_count=20
        )
        return SimpleNamespace(text=reply, usage_metadata=usage)


def _extractor(tmp_path: Path, replies: list[Any]) -> tuple[GeminiExtractor, _FakeModels]:
    models = _FakeModels(replies)
    client: Any = SimpleNamespace(models=models)
    return GeminiExtractor("fake-model", tmp_path, client=client), models


def test_reply_is_parsed_and_tokens_counted(tmp_path: Path) -> None:
    extractor, _ = _extractor(tmp_path, [_REPLY])
    result = extractor.extract("doc1", "some text")
    assert result.valid and not result.cached
    assert result.extraction.results[0].value == "12,7"
    assert (result.input_tokens, result.output_tokens) == (500, 100)  # thinking billed as output


def test_second_run_is_served_from_the_cache(tmp_path: Path) -> None:
    extractor, models = _extractor(tmp_path, [_REPLY])
    extractor.extract("doc1", "some text")
    again = extractor.extract("doc1", "some text")
    assert again.cached and models.calls == 1


def test_changed_text_is_not_served_a_stale_answer(tmp_path: Path) -> None:
    extractor, models = _extractor(tmp_path, [_REPLY])
    extractor.extract("doc1", "some text")
    extractor.extract("doc1", "re-OCRed text")
    assert models.calls == 2


def test_a_reply_that_breaks_the_schema_counts_as_empty(tmp_path: Path) -> None:
    extractor, _ = _extractor(tmp_path, ['{"patient_name": "x"}'])
    result = extractor.extract("doc1", "some text")
    assert not result.valid and result.extraction.results == []


def test_daily_quota_stops_the_run(tmp_path: Path) -> None:
    quota = errors.ClientError(
        429, {"error": {"message": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}}
    )
    extractor, _ = _extractor(tmp_path, [quota])
    with pytest.raises(QuotaExhausted):
        extractor.extract("doc1", "some text")


def test_a_busy_service_is_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("extract.llm.time.sleep", lambda _: None)
    busy = errors.ServerError(503, {"error": {"message": "overloaded"}})
    extractor, models = _extractor(tmp_path, [busy, busy, _REPLY])
    assert extractor.extract("doc1", "some text").valid
    assert models.calls == 3


def test_a_stalled_connection_times_out_and_is_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("extract.llm.time.sleep", lambda _: None)
    extractor, models = _extractor(tmp_path, [httpx.ReadTimeout("stalled"), _REPLY])
    assert extractor.extract("doc1", "some text").valid
    assert models.calls == 2
