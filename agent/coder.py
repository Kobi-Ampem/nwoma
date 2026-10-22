"""The coding agent: Gemini with tools assigns LOINC and ICD-10-CM codes, in at most 5 steps.

Search alone misses what needs knowledge: 'VGM' is the French abbreviation of mean corpuscular
volume (MCV), 'Kaliémie' means potassium in blood. The agent can rephrase a search, compare
candidates against the unit and the document, and choose. Each step is one model call; the
model may call several tools at once. On the last step it must call `submit_codes`, so a run
always ends with an answer. Runs are cached on disk like the extractor's.

The prompt's own examples ('TSH', 'Ferritinémie') appear nowhere in the evaluation data, so they
cannot hand the agent an answer.
"""

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google import genai
from google.genai import errors, types

from extract.llm import QuotaExhausted
from normalise.fields import parse_number, parse_range
from normalise.icd10 import Icd10Mapper
from normalise.loinc import LoincMapper

MAX_STEPS = 5
_RETRIES = 4

PROMPT = """You assign standard codes to items extracted from a clinical document.
Lab results get a LOINC code; diagnoses get an ICD-10-CM code.

How to work:
- Use search_loinc and search_icd10 to find candidates. You may call several tools at once.
- If no candidate fits, search again with a better query: expand abbreviations and translate
  French terms to English (e.g. 'TSH' -> 'thyrotropin', 'Ferritinémie' -> 'ferritin serum').
- LOINC: the unit decides the property (mg/dL is mass, mmol/L or µmol/L is moles, G/L or 10³/µL
  is a count). Results on a general lab report are in serum/plasma or blood unless the name or
  section says urine. Prefer the common, general code over a method-specific one.
- ICD-10-CM: code only what is written. With no detail, use the 'unspecified' or 'without
  complications' code. Diabetes of unstated type is type 2 (E11).
- Use read_document if you need context such as the section heading of a result.
- Finish by calling submit_codes once, with one code for every item id. You have at most
  {steps} steps.

Document type: {doc_type}
Items:
{items}
"""


@dataclass
class AgentRun:
    codes: dict[str, str]  # item id -> code
    steps: int
    tool_calls: list[str]
    input_tokens: int
    output_tokens: int
    seconds: float
    cached: bool = False


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


_TOOLS = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="search_loinc",
            description="Top 5 LOINC codes for a lab test name, ranked using the unit.",
            parameters_json_schema=_schema(
                {"name": {"type": "string"}, "unit": {"type": "string"}}, ["name"]
            ),
        ),
        types.FunctionDeclaration(
            name="search_icd10",
            description="Top 5 ICD-10-CM codes for a diagnosis, in English or French.",
            parameters_json_schema=_schema({"diagnosis": {"type": "string"}}, ["diagnosis"]),
        ),
        types.FunctionDeclaration(
            name="check_range",
            description="Whether a result value is high, low or normal for its reference range.",
            parameters_json_schema=_schema(
                {"value": {"type": "string"}, "ref_range": {"type": "string"}},
                ["value", "ref_range"],
            ),
        ),
        types.FunctionDeclaration(
            name="read_document",
            description="Lines of the document containing any of the given words.",
            parameters_json_schema=_schema({"words": {"type": "string"}}, ["words"]),
        ),
        types.FunctionDeclaration(
            name="submit_codes",
            description="Final answer: one code per item id. Call once, at the end.",
            parameters_json_schema=_schema(
                {
                    "codes": {
                        "type": "array",
                        "items": _schema(
                            {"id": {"type": "string"}, "code": {"type": "string"}},
                            ["id", "code"],
                        ),
                    }
                },
                ["codes"],
            ),
        ),
    ]
)


class CodingAgent:
    def __init__(
        self,
        model: str,
        loinc: LoincMapper,
        icd10: Icd10Mapper,
        cache_dir: Path,
        client: genai.Client | None = None,
    ) -> None:
        self.model = model
        self.loinc = loinc
        self.icd10 = icd10
        self.cache_dir = cache_dir / model
        self.client = client or genai.Client(http_options=types.HttpOptions(timeout=60_000))

    def _tools(self, text: str) -> dict[str, Callable[..., Any]]:
        def search_loinc(name: str, unit: str | None = None) -> list[dict[str, str]]:
            return [
                {
                    "code": h.code,
                    "name": self.loinc.rows[h.code]["LONG_COMMON_NAME"],
                    "property": self.loinc.rows[h.code]["PROPERTY"],
                    "specimen": self.loinc.rows[h.code]["SYSTEM"],
                }
                for h in self.loinc.map(name, unit)
            ]

        def search_icd10(diagnosis: str) -> list[dict[str, str]]:
            return [
                {"code": h.code, "description": self.icd10.descriptions[h.code]}
                for h in self.icd10.map(diagnosis)
            ]

        def check_range(value: str, ref_range: str) -> str:
            v, bounds = parse_number(value), parse_range(ref_range)
            if v is None or bounds is None:
                return "unreadable"
            if bounds[1] is not None and v > bounds[1]:
                return "high"
            if bounds[0] is not None and v < bounds[0]:
                return "low"
            return "normal"

        def read_document(words: str) -> list[str]:
            wanted = [w.casefold() for w in words.split() if len(w) > 1]
            lines = [
                line for line in text.splitlines() if any(w in line.casefold() for w in wanted)
            ]
            return lines[:10]

        return {
            "search_loinc": search_loinc,
            "search_icd10": search_icd10,
            "check_range": check_range,
            "read_document": read_document,
        }

    def run(self, doc_id: str, doc_type: str, items: list[dict[str, str]], text: str) -> AgentRun:
        prompt = PROMPT.format(
            steps=MAX_STEPS,
            doc_type=doc_type,
            items="\n".join(json.dumps(item, ensure_ascii=False) for item in items),
        )
        key = hashlib.sha256((prompt + text).encode()).hexdigest()[:12]
        path = self.cache_dir / f"{doc_id}-{key}.json"
        if path.exists():
            return AgentRun(**json.loads(path.read_text()) | {"cached": True})
        result = self._loop(prompt, text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.__dict__ | {"cached": False}, ensure_ascii=False))
        return result

    def _loop(self, prompt: str, text: str) -> AgentRun:
        tools = self._tools(text)
        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part(text=prompt)])
        ]
        calls_made: list[str] = []
        tokens_in = tokens_out = 0
        start = time.perf_counter()
        for step in range(1, MAX_STEPS + 1):
            last = step == MAX_STEPS
            config = types.GenerateContentConfig(
                temperature=0.0,
                tools=[_TOOLS],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                # On the last step the only move left is to answer.
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode=types.FunctionCallingConfigMode.ANY,
                        allowed_function_names=["submit_codes"],
                    )
                )
                if last
                else None,
            )
            response = self._call(contents, config)
            usage = response.usage_metadata
            if usage:
                tokens_in += usage.prompt_token_count or 0
                tokens_out += (usage.candidates_token_count or 0) + (
                    usage.thoughts_token_count or 0
                )
            content = response.candidates[0].content if response.candidates else None
            if content is None or not content.parts:
                break
            contents.append(content)  # kept whole: Gemini needs its own thought signatures back
            replies: list[types.Part] = []
            for part in content.parts:
                call = part.function_call
                if call is None or not call.name:
                    continue
                calls_made.append(call.name)
                args = dict(call.args or {})
                if call.name == "submit_codes":
                    codes = {c["id"]: c["code"] for c in args.get("codes", []) if "id" in c}
                    elapsed = time.perf_counter() - start
                    return AgentRun(codes, step, calls_made, tokens_in, tokens_out, elapsed)
                try:
                    output: Any = tools[call.name](**args)
                except (KeyError, TypeError) as e:  # unknown tool or wrong arguments
                    output = f"error: {e}"
                replies.append(
                    types.Part.from_function_response(name=call.name, response={"result": output})
                )
            if not replies:
                break  # answered in text without submitting: no codes
            contents.append(types.Content(role="user", parts=replies))
        return AgentRun({}, step, calls_made, tokens_in, tokens_out, time.perf_counter() - start)

    def _call(self, contents: list[Any], config: types.GenerateContentConfig) -> Any:
        for attempt in range(_RETRIES):
            try:
                return self.client.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
            except errors.APIError as e:
                if e.code == 429 and "day" in str(e).lower():
                    raise QuotaExhausted(str(e)) from e
                if e.code in (429, 500, 503) and attempt < _RETRIES - 1:
                    time.sleep(2 ** (attempt + 2))
                    continue
                raise
        raise RuntimeError("unreachable")
