// Types mirror the API's responses (api/service.py, extract/schema.py).

export type DocType = 'lab' | 'referral'

export interface ExtractedResult {
  test_name: string
  value: string
  unit: string | null
  ref_range: string | null
  flag: string | null
}

export interface ExtractedMedication {
  name: string
  dose: string | null
  frequency: string | null
}

export interface Extraction {
  patient_name: string | null
  birth_date: string | null
  sex: string | null
  collection_date: string | null
  clinician: string | null
  results: ExtractedResult[]
  reason: string | null
  diagnoses: string[]
  medications: ExtractedMedication[]
  allergies: string[]
}

export interface Issue {
  field: string
  kind: string
  message: string
}

export interface CodeSuggestion {
  code: string
  display: string
}

export interface ExtractResponse {
  doc_id: string
  doc_type: DocType
  text_source: 'text_layer' | 'ocr'
  text: string
  extraction: Extraction
  extractor: 'ner' | 'llm'
  issues: Issue[]
  codes: Record<string, CodeSuggestion[]>
  llm_enabled: boolean
  notes: string[]
  seconds: number
}

export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// fetch() rejects with a bare TypeError ("Failed to fetch") when the server cannot be reached.
export function explain(e: unknown): string {
  if (e instanceof TypeError) {
    return 'The Nwoma server could not be reached. If it has been idle it may be starting up: try again in a minute.'
  }
  return e instanceof Error ? e.message : String(e)
}

async function check(response: Response): Promise<Response> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail ?? `The server answered ${response.status}`)
  }
  return response
}

export async function extract(file: Blob, name: string): Promise<ExtractResponse> {
  const form = new FormData()
  form.append('file', file, name)
  const response = await fetch(`${API_URL}/extract`, { method: 'POST', body: form })
  return (await check(response)).json()
}

export async function samples(): Promise<{ name: string; url: string }[]> {
  return (await check(await fetch(`${API_URL}/samples`))).json()
}

export async function sampleFile(url: string): Promise<Blob> {
  return (await check(await fetch(`${API_URL}${url}`))).blob()
}

// Fresh suggestions after a reviewer edits a test name, unit or diagnosis.
export async function suggestCodes(
  kind: 'lab' | 'diagnosis',
  text: string,
  unit: string | null = null,
): Promise<CodeSuggestion[]> {
  const response = await fetch(`${API_URL}/codes`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ kind, text, unit }),
  })
  return (await check(response)).json()
}

// The validator again, on the extraction as edited: fixed fields stop being flagged.
export async function validate(docType: DocType, extraction: Extraction): Promise<Issue[]> {
  const response = await fetch(`${API_URL}/validate`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ doc_type: docType, extraction }),
  })
  return (await check(response)).json()
}

export interface FhirRequest {
  doc_id: string
  doc_type: DocType
  extraction: Extraction
  codes: Record<string, string>
  confirmed: string[]
  reviewer: string | null
}

export async function toFhir(request: FhirRequest): Promise<unknown> {
  const response = await fetch(`${API_URL}/fhir`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(request),
  })
  return (await check(response)).json()
}
