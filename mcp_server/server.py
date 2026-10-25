"""Nwoma as an MCP server: AI assistants can extract, code and export clinical documents.

    uv run python -m mcp_server.server        # stdio, for Claude Desktop, Claude Code, etc.

Same service layer as the HTTP API, so both behave the same. The models load on the first tool
call, not at start-up, so an assistant can list the tools instantly. Everything runs locally;
documents are read from the user's own disk and nothing is stored.
"""

from functools import cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from api.fhir import FhirRequest, build_bundle
from api.service import MAX_BYTES, Nwoma

load_dotenv()

server = MCPServer(
    name="nwoma",
    instructions=(
        "Nwoma reads clinical documents (lab reports and referral letters, English or French, "
        "digital or scanned) and returns their fields, issues a human should review, and "
        "suggested LOINC and ICD-10-CM codes. It transcribes; it never diagnoses or advises."
    ),
)


@cache
def _nwoma() -> Nwoma:
    return Nwoma()


@server.tool()
def extract_document(path: str) -> dict[str, Any]:
    """Extract a lab report or referral letter from a PDF or image on this computer.

    Returns the document type, every field as printed, issues the reviewer should check, and
    the top 5 LOINC or ICD-10-CM codes for each lab result and diagnosis.
    """
    file = Path(path).expanduser()
    if not file.is_file():
        raise ValueError(f"no file at {file}")
    if file.stat().st_size > MAX_BYTES:
        raise ValueError("documents are limited to 5 MB")
    return _nwoma().extract(file.read_bytes()).model_dump()


@server.tool()
def suggest_lab_codes(test_name: str, unit: str | None = None) -> list[dict[str, str]]:
    """Top 5 LOINC codes for a lab test name as printed (English or French). The unit decides
    between mass and molar codes: creatinine in µmol/L is not the same code as in mg/dL."""
    return [c.model_dump() for c in _nwoma().lab_codes(test_name, unit)]


@server.tool()
def suggest_diagnosis_codes(diagnosis: str) -> list[dict[str, str]]:
    """Top 5 ICD-10-CM codes for a diagnosis as written (English or French), following the
    coding rule that undocumented detail is coded as unspecified."""
    return [c.model_dump() for c in _nwoma().diagnosis_codes(diagnosis)]


@server.tool()
def to_fhir(request: FhirRequest) -> dict[str, Any]:
    """Turn a reviewed extraction into a FHIR R4 Bundle. Pass the chosen code per item in
    `codes`, and the field paths a human confirmed in `confirmed` with the `reviewer`'s name:
    they are recorded as Provenance."""
    return build_bundle(request)


if __name__ == "__main__":
    server.run("stdio")
