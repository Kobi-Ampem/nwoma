"""The coding agent's loop with a scripted fake model: offline, free and deterministic."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

from google.genai import types

from agent.coder import MAX_STEPS, CodingAgent
from normalise.retrieval import Hit


class _Mapper:
    """Stands in for both mappers: returns one fixed candidate."""

    rows: ClassVar = {
        "2823-3": {"LONG_COMMON_NAME": "Potassium", "PROPERTY": "SCnc", "SYSTEM": "Ser/Plas"}
    }
    descriptions: ClassVar = {"E11.9": "Type 2 diabetes mellitus without complications"}

    def map(self, *_: Any, **__: Any) -> list[Hit]:
        return [Hit("2823-3", 1.0, 1, 1)]


def _reply(*calls: tuple[str, dict[str, Any]]) -> Any:
    parts = [types.Part(function_call=types.FunctionCall(name=n, args=a)) for n, a in calls]
    usage = SimpleNamespace(
        prompt_token_count=100, candidates_token_count=20, thoughts_token_count=0
    )
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=types.Content(role="model", parts=parts))],
        usage_metadata=usage,
    )


class _Model:
    def __init__(self, replies: list[Any]) -> None:
        self.replies = replies
        self.configs: list[Any] = []

    def generate_content(self, **kw: Any) -> Any:
        self.configs.append(kw["config"])
        return self.replies[min(len(self.configs) - 1, len(self.replies) - 1)]


def _agent(tmp_path: Path, replies: list[Any]) -> tuple[CodingAgent, _Model]:
    model = _Model(replies)
    client: Any = SimpleNamespace(models=model)
    mapper: Any = _Mapper()
    return CodingAgent("fake", mapper, mapper, tmp_path, client=client), model


ITEMS = [{"id": "r0", "test": "Kaliémie", "unit": "mmol/L"}]


def test_the_agent_searches_then_submits(tmp_path: Path) -> None:
    agent, _ = _agent(
        tmp_path,
        [
            _reply(("search_loinc", {"name": "potassium serum", "unit": "mmol/L"})),
            _reply(("submit_codes", {"codes": [{"id": "r0", "code": "2823-3"}]})),
        ],
    )
    run = agent.run("doc1", "lab", ITEMS, "Kaliémie 4,0 mmol/L")
    assert run.codes == {"r0": "2823-3"} and run.steps == 2
    assert run.tool_calls == ["search_loinc", "submit_codes"]
    assert run.input_tokens == 200


def test_the_last_step_can_only_submit(tmp_path: Path) -> None:
    # A model that never stops searching is forced to answer on the last step.
    agent, model = _agent(tmp_path, [_reply(("read_document", {"words": "potassium"}))])
    run = agent.run("doc1", "lab", ITEMS, "Kaliémie 4,0 mmol/L")
    assert run.steps == MAX_STEPS and run.codes == {}
    assert model.configs[-1].tool_config is not None  # forced to submit_codes
    assert all(c.tool_config is None for c in model.configs[:-1])


def test_a_second_run_is_served_from_the_cache(tmp_path: Path) -> None:
    replies = [_reply(("submit_codes", {"codes": [{"id": "r0", "code": "2823-3"}]}))]
    agent, model = _agent(tmp_path, replies)
    agent.run("doc1", "lab", ITEMS, "text")
    again = agent.run("doc1", "lab", ITEMS, "text")
    assert again.cached and len(model.configs) == 1


def test_a_tool_called_with_odd_arguments_does_not_crash_the_run(tmp_path: Path) -> None:
    # Gemini once passed read_document a list where the schema says a string.
    agent, _ = _agent(
        tmp_path,
        [
            _reply(
                ("read_document", {"words": ["potassium", "serum"]}), ("search_icd10", {"bad": 1})
            ),
            _reply(("submit_codes", {"codes": [{"id": "r0", "code": "2823-3"}]})),
        ],
    )
    run = agent.run("doc1", "lab", ITEMS, "Kaliémie 4,0 mmol/L\nPotassium serum")
    assert run.codes == {"r0": "2823-3"}
