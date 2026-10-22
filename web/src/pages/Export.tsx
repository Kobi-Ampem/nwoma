import { useState } from 'react'
import { explain, toFhir } from '../api'
import { Stepper } from '../components/Stepper'
import { allPaths } from '../review'
import type { Session } from '../session'

export function Export(props: { session: Session; reviewer: string; setReviewer: (name: string) => void }) {
  const { session, reviewer, setReviewer } = props
  const { response, ext, confirmed, codes } = session
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const paths = allPaths(ext, response.doc_type, codes)
  const done = paths.filter((p) => confirmed.has(p)).length
  const codeKeys = Object.keys(codes).filter((k) => codes[k])
  const codesDone = codeKeys.filter((k) => confirmed.has(`${k}.code`)).length
  // Confirmations are recorded as "verified by <reviewer>": a name is required once there are any.
  const needsName = confirmed.size > 0 && reviewer.trim() === ''

  async function download() {
    setBusy(true)
    setError(null)
    try {
      const bundle = await toFhir({
        doc_id: response.doc_id,
        doc_type: response.doc_type,
        extraction: ext,
        codes: Object.fromEntries(codeKeys.map((k) => [k, codes[k]])),
        confirmed: [...confirmed],
        reviewer: reviewer.trim() || null,
      })
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/fhir+json' })
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = `nwoma-${response.doc_id}.fhir.json`
      link.click()
      URL.revokeObjectURL(link.href)
    } catch (e) {
      setError(explain(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Stepper at={3} />
      <div className="export-grid">
        <section className="card card-pad">
          <h1 style={{ fontSize: 24, marginBottom: 14 }}>Ready to export</h1>
          <dl className="kv">
            <dt>Patient</dt>
            <dd>{ext.patient_name ?? '—'}</dd>
            <dt>Date of birth</dt>
            <dd>{ext.birth_date ?? '—'}</dd>
            <dt>Document</dt>
            <dd>
              {response.doc_type === 'lab' ? `Lab report, ${ext.results.length} results` : `Referral letter, ${ext.diagnoses.length} diagnoses`}
            </dd>
          </dl>
          <div className="tiles">
            <div className="tile">
              <b>
                {done}/{paths.length}
              </b>
              <span>fields and codes confirmed</span>
            </div>
            <div className="tile">
              <b>
                {codesDone}/{codeKeys.length}
              </b>
              <span>codes confirmed</span>
            </div>
            <div className="tile">
              <b>{response.issues.length}</b>
              <span>fields were flagged</span>
            </div>
          </div>
          <p className="muted small">
            Unconfirmed fields are still exported, marked as machine-extracted. Only what you confirmed is recorded as
            verified by you. <a href="#/review">Back to review</a>
          </p>
        </section>

        <section className="card card-pad download">
          <div className="field">
            <label htmlFor="reviewer">Reviewer name {confirmed.size > 0 && '(required)'}</label>
            <input id="reviewer" className="input" value={reviewer} placeholder="e.g. Dr A. Mensah" onChange={(e) => setReviewer(e.target.value)} />
            {needsName && <span className="hint">Your confirmations are recorded under your name.</span>}
          </div>
          <div className="option">
            <span className="chip chip-brand">JSON</span>
            <div>
              <h3>FHIR bundle, for health systems</h3>
              <p className="muted small">
                FHIR R4 is the standard format electronic records import. Includes LOINC and ICD-10-CM codes and a
                Provenance record of what you verified.
              </p>
              <button className="btn btn-primary" disabled={needsName || busy} onClick={download}>
                {busy ? 'Preparing…' : 'Download FHIR bundle'}
              </button>
            </div>
          </div>
          <div className="option">
            <span className="chip">PDF</span>
            <div>
              <h3>Readable summary, for people</h3>
              <p className="muted small">A one-page summary of the extracted record, to read, print or save as PDF.</p>
              <a className={`btn ${needsName ? 'disabled' : ''}`} href="#/summary" aria-disabled={needsName} onClick={(e) => needsName && e.preventDefault()}>
                Open readable summary
              </a>
            </div>
          </div>
          {error && <p className="error-box">{error}</p>}
        </section>
      </div>
    </>
  )
}
