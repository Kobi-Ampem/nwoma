import { describe, expect, it } from 'vitest'
import type { Extraction } from './api'
import { fieldRows, locate, setField } from './review'

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

  it('finds fields in the text, across line breaks, without overlaps', () => {
    const text = 'Name: MENSAH Ama\nGlucose 140 mg/dL 70 -\n99 H'
    const found = locate(text, fieldRows(lab, 'lab'))
    const byPath = Object.fromEntries(found.map((h) => [h.path, text.slice(h.start, h.end)]))
    expect(byPath['patient_name']).toBe('MENSAH Ama')
    expect(byPath['results[0].ref_range']).toBe('70 -\n99')
    expect(byPath['results[0].flag']).toBeUndefined() // one letter: too short to place safely
  })

  it('gives every diagnosis its own group, so each gets a code choice', () => {
    const letter = { ...lab, results: [], diagnoses: ['Anémie', 'Obésité'] }
    const groups = new Set(fieldRows(letter, 'referral').filter((r) => r.path.startsWith('diagnoses')).map((r) => r.group))
    expect(groups.size).toBe(2)
  })
})
