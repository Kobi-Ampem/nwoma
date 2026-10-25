// Review logic, kept out of the components so it can be tested on its own.
import type { DocType, Extraction } from './api'

// One editable field, addressed by its path, e.g. 'results[3].flag'.
export interface FieldRow {
  path: string
  label: string
  value: string
}

export const HEADER_FIELDS: { key: keyof Extraction; label: string; types: DocType[] }[] = [
  { key: 'patient_name', label: 'Patient', types: ['lab', 'referral'] },
  { key: 'birth_date', label: 'Date of birth', types: ['lab', 'referral'] },
  { key: 'sex', label: 'Sex', types: ['lab', 'referral'] },
  { key: 'collection_date', label: 'Collected', types: ['lab'] },
  { key: 'clinician', label: 'Clinician', types: ['lab', 'referral'] },
  { key: 'reason', label: 'Reason for referral', types: ['referral'] },
]

export const RESULT_FIELDS = ['test_name', 'value', 'unit', 'ref_range', 'flag'] as const
export const MEDICATION_FIELDS = ['name', 'dose', 'frequency'] as const

// Every editable field of the extraction, in reading order.
export function fieldRows(ext: Extraction, docType: DocType): FieldRow[] {
  const rows: FieldRow[] = HEADER_FIELDS.filter((f) => f.types.includes(docType)).map((f) => ({
    path: f.key,
    label: f.label,
    value: (ext[f.key] as string | null) ?? '',
  }))
  ext.results.forEach((r, i) =>
    RESULT_FIELDS.forEach((f) => rows.push({ path: `results[${i}].${f}`, label: f, value: r[f] ?? '' })),
  )
  ext.diagnoses.forEach((d, i) => rows.push({ path: `diagnoses[${i}]`, label: 'diagnosis', value: d }))
  ext.medications.forEach((m, i) =>
    MEDICATION_FIELDS.forEach((f) => rows.push({ path: `medications[${i}].${f}`, label: f, value: m[f] ?? '' })),
  )
  ext.allergies.forEach((a, i) => rows.push({ path: `allergies[${i}]`, label: 'allergy', value: a }))
  return rows
}

// The paths one review item covers. A coded item includes its code: confirming a row confirms
// the code chosen for it, and only then is the FHIR resource marked human-verified.
export function itemPaths(key: string, coded: boolean): string[] {
  const m = /^(\w+)\[(\d+)\]$/.exec(key)
  if (!m) return [key]
  const [, list, i] = m
  const fields =
    list === 'results'
      ? RESULT_FIELDS.map((f) => `${key}.${f}`)
      : list === 'medications'
        ? MEDICATION_FIELDS.map((f) => `${key}.${f}`)
        : [key]
  return coded && (list === 'results' || list === 'diagnoses') && i !== undefined ? [...fields, `${key}.code`] : fields
}

// Every path the reviewer can confirm, for the progress bar.
export function allPaths(ext: Extraction, docType: DocType, codes: Record<string, string>): string[] {
  const paths = HEADER_FIELDS.filter((f) => f.types.includes(docType)).map((f) => f.key as string)
  const keys = [
    ...ext.results.map((_, i) => `results[${i}]`),
    ...ext.diagnoses.map((_, i) => `diagnoses[${i}]`),
    ...ext.medications.map((_, i) => `medications[${i}]`),
    ...ext.allergies.map((_, i) => `allergies[${i}]`),
  ]
  keys.forEach((k) => paths.push(...itemPaths(k, Boolean(codes[k]))))
  return paths
}

// The codes that go into the export: only those the reviewer confirmed. The top suggestion is
// preselected for convenience and is right first time only about half the time, so an
// unconfirmed one must not reach a records system looking like a chosen code.
export function exportedCodes(codes: Record<string, string>, confirmed: Set<string>): Record<string, string> {
  return Object.fromEntries(Object.entries(codes).filter(([k, code]) => code && confirmed.has(`${k}.code`)))
}

const PATH = /^(\w+)(?:\[(\d+)\])?(?:\.(\w+))?$/

// A copy of the extraction with one field changed. Empty text becomes null where allowed.
export function setField(ext: Extraction, path: string, value: string): Extraction {
  const match = PATH.exec(path)
  if (!match) return ext
  const [, key, index, sub] = match
  const next = structuredClone(ext) as unknown as Record<string, unknown>
  if (index === undefined) {
    next[key] = value === '' ? null : value
  } else if (sub === undefined) {
    ;(next[key] as string[])[Number(index)] = value
  } else {
    const item = (next[key] as Record<string, string | null>[])[Number(index)]
    item[sub] = value === '' && sub !== 'test_name' && sub !== 'name' && sub !== 'value' ? null : value
  }
  return next as unknown as Extraction
}

// Edits that change which code is right: a lab test's name or unit, or a diagnosis.
export function codeKeyAffectedBy(path: string): string | null {
  const m = /^(results\[\d+\])\.(test_name|unit)$/.exec(path) ?? /^(diagnoses\[\d+\])$/.exec(path)
  return m ? m[1] : null
}

export interface Highlight {
  start: number
  end: number
  path: string
}

function escape(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// Where each field's text sits in the document text, so it can be highlighted. Whitespace is
// flexible (a wrapped value spans lines); each field takes the first match not already used.
export function locate(text: string, rows: FieldRow[]): Highlight[] {
  const taken: Highlight[] = []
  for (const row of rows) {
    const words = row.value.trim().split(/\s+/).filter(Boolean)
    if (words.length === 0 || row.value.trim().length < 2) continue // too short to find safely
    const pattern = new RegExp(words.map(escape).join('\\s+'), 'g')
    for (const m of text.matchAll(pattern)) {
      const start = m.index ?? 0
      const end = start + m[0].length
      if (!taken.some((h) => start < h.end && h.start < end)) {
        taken.push({ start, end, path: row.path })
        break
      }
    }
  }
  return taken.sort((a, b) => a.start - b.start)
}
