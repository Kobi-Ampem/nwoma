import { useState } from 'react'
import { explain, toFhir } from '../api'
import { allPaths, exportedCodes } from '../review'
import type { Session } from '../session'

// The last section of the review workspace: who reviewed, and the two outputs.
export function ExportPanel(props: { session: Session; reviewer: string; setReviewer: (name: string) => void }) {
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
        codes: exportedCodes(codes, confirmed),
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
    <section className="card export-panel" id="export">
      <header>
        <h2>Export</h2>
        <span className="muted small">
          {done} of {paths.length} fields and codes confirmed · {codesDone} of {codeKeys.length} codes
        </span>
      </header>
      <div className="export-body">
        <div className="field">
          <label htmlFor="reviewer">Reviewer name {confirmed.size > 0 && '(required)'}</label>
          <input id="reviewer" className="input" value={reviewer} placeholder="e.g. Dr A. Mensah" onChange={(e) => setReviewer(e.target.value)} />
          {needsName ? (
            <span className="hint">Your confirmations are recorded under your name.</span>
          ) : (
            <span className="muted small">Unconfirmed fields are exported as machine-extracted; unconfirmed codes are left out.</span>
          )}
        </div>
        <div className="download">
          <div className="option">
            <span className="chip chip-brand">JSON</span>
            <div>
              <h3>FHIR bundle, for health systems</h3>
              <p className="muted small">The standard format electronic records import, with codes and a record of what you verified.</p>
              <button className="btn btn-primary" disabled={needsName || busy} onClick={download}>
                {busy ? 'Preparing…' : 'Download FHIR bundle'}
              </button>
            </div>
          </div>
          <div className="option">
            <span className="chip">PDF</span>
            <div>
              <h3>Readable summary, for people</h3>
              <p className="muted small">A one-page summary to read, print or save as PDF.</p>
              <a className={`btn ${needsName ? 'disabled' : ''}`} href="#/summary" aria-disabled={needsName} onClick={(e) => needsName && e.preventDefault()}>
                Open readable summary
              </a>
            </div>
          </div>
        </div>
        {error && <p className="error-box">{error}</p>}
      </div>
    </section>
  )
}
