import { describe, expect, it } from 'vitest'
import type { Extraction } from './api'
import { allPaths, codeKeyAffectedBy, exportedCodes, fieldRows, itemPaths, locate, setField } from './review'

const lab: Extraction = {
  patient_name: 'MENSAH Ama',
  birth_date: '05/04/1990',
  sex: 'F',
  collection_date: '21/03/2024',
  clinician: 'Kwame Boateng',
  results: [{ test_name: 'Glucose', value: '140', unit: 'mg/dL', ref_range: '70 - 99', flag: 'H' }],
  reason: null,
  diagnoses: [],
  medications: [],
  allergies: [],
}

describe('review', () => {
  it('lists header fields and every result field for a lab report', () => {
    const paths = fieldRows(lab, 'lab').map((r) => r.path)
    expect(paths).toContain('collection_date')
    expect(paths).not.toContain('reason')
    expect(paths).toContain('results[0].flag')
  })

  it('edits a nested field without touching the original', () => {
    const edited = setField(lab, 'results[0].flag', '')
    expect(edited.results[0].flag).toBeNull()
    expect(lab.results[0].flag).toBe('H')
    expect(setField(lab, 'patient_name', 'Ama Mensah').patient_name).toBe('Ama Mensah')
  })

  it('makes a coded row include its code, so confirming the row confirms the code', () => {
    expect(itemPaths('results[0]', true)).toContain('results[0].code')
    expect(itemPaths('results[0]', false)).not.toContain('results[0].code')
    expect(itemPaths('diagnoses[2]', true)).toEqual(['diagnoses[2]', 'diagnoses[2].code'])
    expect(itemPaths('patient_name', true)).toEqual(['patient_name'])
  })

  it('knows which edits invalidate a code', () => {
    // Codex audit #3: correcting mg/dL to µmol/L must not keep the mass-concentration code.
    expect(codeKeyAffectedBy('results[3].unit')).toBe('results[3]')
    expect(codeKeyAffectedBy('results[3].test_name')).toBe('results[3]')
    expect(codeKeyAffectedBy('results[3].value')).toBeNull()
    expect(codeKeyAffectedBy('diagnoses[1]')).toBe('diagnoses[1]')
    expect(codeKeyAffectedBy('medications[0].dose')).toBeNull()
  })

  it('counts every header field, result field and chosen code for progress', () => {
    const paths = allPaths(lab, 'lab', { 'results[0]': '2345-7' })
    expect(paths).toHaveLength(5 + 5 + 1) // header, result fields, its code
  })

  it('finds fields in the text, across line breaks, without overlaps', () => {
    const text = 'Name: MENSAH Ama\nGlucose 140 mg/dL 70 -\n99 H'
    const found = locate(text, fieldRows(lab, 'lab'))
    const byPath = Object.fromEntries(found.map((h) => [h.path, text.slice(h.start, h.end)]))
    expect(byPath['patient_name']).toBe('MENSAH Ama')
    expect(byPath['results[0].ref_range']).toBe('70 -\n99')
    expect(byPath['results[0].flag']).toBeUndefined() // one letter: too short to place safely
  })

  it('exports only the codes the reviewer confirmed', () => {
    const codes = { 'results[0]': '2345-7', 'results[1]': '2951-2', 'diagnoses[0]': '' }
    const confirmed = new Set(['results[0].code', 'diagnoses[0].code'])
    expect(exportedCodes(codes, confirmed)).toEqual({ 'results[0]': '2345-7' })
  })
})
