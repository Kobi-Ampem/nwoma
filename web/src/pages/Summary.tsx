import { useState } from 'react'
import type { Session } from '../session'

// A printable summary for people; the FHIR bundle is the machine version of the same record.
export function Summary({ session, reviewer }: { session: Session; reviewer: string }) {
  const { response, ext, confirmed, codes, suggestions } = session
  const display = (key: string) => suggestions[key]?.find((s) => s.code === codes[key])?.display ?? ''
  const mark = (ok: boolean) => (ok ? '✓' : '')
  const rowOk = (key: string, fields: string[]) => fields.every((f) => confirmed.has(`${key}.${f}`))
  const [today] = useState(() => new Date().toISOString().slice(0, 10)) // fixed when the page opens

  return (
    <article className="card card-pad summary-sheet">
      <div className="no-print" style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginBottom: 12 }}>
        <a className="btn btn-ghost" href="#/review">
          ← Back
        </a>
        <button className="btn btn-primary" onClick={() => window.print()}>
          Print or save as PDF
        </button>
      </div>
      <p className="eyebrow">Nwoma · extracted record</p>
      <h1>{response.doc_type === 'lab' ? 'Laboratory report' : 'Referral letter'}</h1>
      <p className="muted small">
        Exported {today}
        {reviewer.trim() ? `, reviewed by ${reviewer.trim()}` : ', not reviewed'}. ✓ marks what the reviewer confirmed.
        Transcribed from a synthetic document; not clinical advice.
      </p>
      <table>
        <tbody>
          <tr><th>Patient</th><td>{ext.patient_name}</td><td>{mark(confirmed.has('patient_name'))}</td></tr>
          <tr><th>Date of birth</th><td>{ext.birth_date}</td><td>{mark(confirmed.has('birth_date'))}</td></tr>
          <tr><th>Sex</th><td>{ext.sex}</td><td>{mark(confirmed.has('sex'))}</td></tr>
          <tr><th>Clinician</th><td>{ext.clinician}</td><td>{mark(confirmed.has('clinician'))}</td></tr>
          {response.doc_type === 'lab' && <tr><th>Collected</th><td>{ext.collection_date}</td><td>{mark(confirmed.has('collection_date'))}</td></tr>}
          {response.doc_type === 'referral' && <tr><th>Reason</th><td>{ext.reason}</td><td>{mark(confirmed.has('reason'))}</td></tr>}
        </tbody>
      </table>
      {response.doc_type === 'lab' && (
        <>
          <h2>Results</h2>
          <table>
            <thead><tr><th>Test</th><th>Value</th><th>Range</th><th>Flag</th><th>LOINC</th><th /></tr></thead>
            <tbody>
              {ext.results.map((r, i) => {
                const key = `results[${i}]`
                return (
                  <tr key={key}>
                    <td>{r.test_name}</td>
                    <td>{r.value} {r.unit}</td>
                    <td>{r.ref_range}</td>
                    <td>{r.flag}</td>
                    <td>{codes[key] ? `${codes[key]} ${display(key)}` : ''}</td>
                    <td>{mark(rowOk(key, ['test_name', 'value', 'unit', 'ref_range', 'flag']))}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </>
      )}
      {response.doc_type === 'referral' && (
        <>
          <h2>Diagnoses</h2>
          <table>
            <tbody>
              {ext.diagnoses.map((d, i) => {
                const key = `diagnoses[${i}]`
                return (
                  <tr key={key}><td>{d}</td><td>{codes[key] ? `${codes[key]} ${display(key)}` : ''}</td><td>{mark(confirmed.has(key))}</td></tr>
                )
              })}
            </tbody>
          </table>
          <h2>Medications</h2>
          <table>
            <tbody>
              {ext.medications.length === 0 && <tr><td className="muted">None listed</td></tr>}
              {ext.medications.map((m, i) => (
                <tr key={i}><td>{m.name}</td><td>{m.dose}</td><td>{m.frequency}</td><td>{mark(rowOk(`medications[${i}]`, ['name', 'dose', 'frequency']))}</td></tr>
              ))}
            </tbody>
          </table>
          <h2>Allergies</h2>
          <table>
            <tbody>
              {ext.allergies.length === 0 && <tr><td className="muted">None listed</td></tr>}
              {ext.allergies.map((a, i) => (
                <tr key={i}><td>{a}</td><td>{mark(confirmed.has(`allergies[${i}]`))}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </article>
  )
}
