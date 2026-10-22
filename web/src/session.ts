import type { CodeSuggestion, ExtractResponse, Extraction } from './api'

// One document under review. Held in the browser only: nothing is sent back until export.
export interface Session {
  response: ExtractResponse
  ext: Extraction // as edited by the reviewer
  confirmed: Set<string> // field paths, and '<item>.code' for confirmed codes
  codes: Record<string, string> // 'results[3]' / 'diagnoses[0]' -> chosen code ('' = none)
  suggestions: Record<string, CodeSuggestion[]>
  file: Blob
  fileName: string
  isPdf: boolean
}

export function startSession(response: ExtractResponse, file: Blob, fileName: string): Session {
  return {
    response,
    ext: response.extraction,
    confirmed: new Set(),
    // The top suggestion is preselected but not confirmed: the reviewer has to accept it.
    codes: Object.fromEntries(Object.entries(response.codes).map(([k, v]) => [k, v[0]?.code ?? ''])),
    suggestions: response.codes,
    file,
    fileName,
    isPdf: file.type === 'application/pdf' || fileName.toLowerCase().endsWith('.pdf'),
  }
}
