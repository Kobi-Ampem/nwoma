import { useState } from 'react'

const KINDS = [
  { label: 'Lab report', prefix: 'lab-report' },
  { label: 'Referral letter', prefix: 'referral-letter' },
] as const
const VARIANTS = [
  { label: 'English', sub: 'digital', suffix: 'en-digital' },
  { label: 'English', sub: 'scanned', suffix: 'en-scanned' },
  { label: 'French', sub: 'digital', suffix: 'fr-digital' },
  { label: 'French', sub: 'scanned', suffix: 'fr-scanned' },
] as const

export function Home(props: {
  samples: { name: string; url: string }[]
  busy: boolean
  slow: boolean
  error: string | null
  onFile: (file: Blob, name: string) => void
  onSample: (url: string, name: string) => void
}) {
  const { samples, busy, slow, error, onFile, onSample } = props
  const [drag, setDrag] = useState(false)
  const byName = new Map(samples.map((s) => [s.name, s.url]))

  return (
    <>
      <section className="hero">
        <div>
          <h1>
            Clinical documents in, <span>coded and verified</span> records out.
          </h1>
          <p className="lead">
            Upload a lab report or a referral letter, in English or French, digital or scanned. Nwoma extracts every
            field, suggests LOINC and ICD-10 codes, flags what needs checking, and exports a FHIR record. It transcribes;
            it never diagnoses.
          </p>
          <a className="btn" href="#/how">
            How it works
          </a>
        </div>

        <div className="card card-pad start">
          <label
            className={`dropzone ${drag ? 'drag' : ''}`}
            onDragOver={(e) => {
              e.preventDefault()
              setDrag(true)
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDrag(false)
              const file = e.dataTransfer.files[0]
              if (file && !busy) onFile(file, file.name)
            }}
          >
            <input
              type="file"
              accept="application/pdf,image/*"
              disabled={busy}
              onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0], e.target.files[0].name)}
            />
            <b>Drop a document or choose a file</b>
            <span className="muted small">PDF or image · up to 5 MB and 5 pages</span>
            <span className="muted small">Test documents only: this public demo is not for real patient data.</span>
          </label>

          <p className="small muted" style={{ margin: '18px 0 8px' }}>
            Or open a sample:
          </p>
          <div className="sample-grid" role="group" aria-label="Sample documents">
            {KINDS.map((kind) => (
              <div key={kind.prefix} className="sample-row">
                <span className="sample-kind">{kind.label}</span>
                {VARIANTS.map((v) => {
                  const name = `${kind.prefix}-${v.suffix}.pdf`
                  const url = byName.get(name)
                  return (
                    <button
                      key={name}
                      className="sample-btn"
                      disabled={busy || !url}
                      onClick={() => url && onSample(url, name)}
                      title={`${kind.label}, ${v.label}, ${v.sub}`}
                    >
                      {v.label}
                      <small>{v.sub}</small>
                    </button>
                  )
                })}
              </div>
            ))}
          </div>

          {busy && (
            <div className="busy" role="status">
              <span className="spinner" />
              {slow ? 'Waking the server up: the first request after a quiet spell can take a minute or two.' : 'Reading the document…'}
            </div>
          )}
          {error && (
            <p className="error-box" role="alert" style={{ marginTop: 14 }}>
              {error}
            </p>
          )}
        </div>
      </section>

      <div className="trust">
        <div className="card">
          <h3>Nothing is stored</h3>
          <p className="muted small">A document is read, answered and forgotten. Review happens in your browser.</p>
        </div>
        <div className="card">
          <h3>A person has the last word</h3>
          <p className="muted small">Uncertain fields are flagged, codes are suggestions, and the export records what you confirmed.</p>
        </div>
        <div className="card">
          <h3>Standard output</h3>
          <p className="muted small">LOINC for tests, ICD-10-CM for diagnoses, FHIR R4 for the record your system imports.</p>
        </div>
      </div>
    </>
  )
}
