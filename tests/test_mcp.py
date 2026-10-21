import asyncio

from mcp_server.server import server


def test_the_four_tools_are_offered_without_loading_models() -> None:
    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == {
        "extract_document",
        "suggest_lab_codes",
        "suggest_diagnosis_codes",
        "to_fhir",
    }
    assert all(t.description for t in tools)  # the assistant decides from these
