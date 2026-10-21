// Review logic, kept out of the components so it can be tested on its own.
import type { Extraction } from './api'

// One editable field on the review form, addressed by its path, e.g. 'results[3].flag'.
export interface FieldRow {
  path: string
  label: string
  value: string
  group: string
}

const HEADER: [keyof Extraction, string][] = [
  ['patient_name', 'Patient'],
  ['birth_date', 'Date of birth'],
  ['sex', 'Sex'],
  ['collection_date', 'Collected'],
  ['clinician', 'Clinician'],
  ['reason', 'Reason for referral'],
]

export function fieldRows(ext: Extraction, docType: 'lab' | 'referral'): FieldRow[] {
  const rows: FieldRow[] = []
  for (const [key, label] of HEADER) {
    if (docType === 'lab' && key === 'reason') continue
    if (docType === 'referral' && key === 'collection_date') continue
    rows.push({ path: key, label, value: (ext[key] as string | null) ?? '', group: 'Patient and document' })
  }
  ext.results.forEach((r, i) => {
    const group = `Result ${i + 1}: ${r.test_name || 'unnamed'}`
    rows.push(
      { path: `results[${i}].test_name`, label: 'Test', value: r.test_name, group },
      { path: `results[${i}].value`, label: 'Value', value: r.value, group },
      { path: `results[${i}].unit`, label: 'Unit', value: r.unit ?? '', group },
      { path: `results[${i}].ref_range`, label: 'Reference range', value: r.ref_range ?? '', group },
      { path: `results[${i}].flag`, label: 'Flag', value: r.flag ?? '', group },
    )
  })
  ext.diagnoses.forEach((d, i) =>
    rows.push({ path: `diagnoses[${i}]`, label: `Diagnosis ${i + 1}`, value: d, group: 'Diagnoses' }),
  )
  ext.medications.forEach((m, i) => {
    const group = `Medication ${i + 1}`
    rows.push(
      { path: `medications[${i}].name`, label: 'Name', value: m.name, group },
      { path: `medications[${i}].dose`, label: 'Dose', value: m.dose ?? '', group },
      { path: `medications[${i}].frequency`, label: 'Frequency', value: m.frequency ?? '', group },
    )
  })
  ext.allergies.forEach((a, i) =>
    rows.push({ path: `allergies[${i}]`, label: `Allergy ${i + 1}`, value: a, group: 'Allergies' }),
  )
  return rows
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
