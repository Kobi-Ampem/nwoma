import { useState } from 'react'
import { HEADLINE, describeSample } from '../data'

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

  return (
    <>
      <section className="hero">
        <div>
          <p className="eyebrow">Nwoma · Asante Twi for “document”</p>
          <h1>
            Clinical documents in, <span>coded and verified</span> records out.
          </h1>
          <p className="lead">
            Lab reports and referral letters, in English or French, digital or scanned. Nwoma reads them, codes every
            test and diagnosis, and shows a clinician only what needs checking. It transcribes; it never diagnoses.
          </p>
          <div className="hero-actions">
            <a className="btn btn-primary" href="#samples">
              Try a sample document
            </a>
            <a className="btn" href="#/how">
              How it works
            </a>
          </div>
        </div>
        <div className="stats">
          <div className="card stat">
            <b>{HEADLINE.cascadeF1}</b>
            <span>field accuracy (F1) on 500 held-out documents</span>
          </div>
          <div className="card stat">
            <b>{HEADLINE.fullyCorrect}</b>
            <span>of documents with every field right, no review needed</span>
          </div>
          <div className="card stat">
            <b>{HEADLINE.toLlm}</b>
            <span>sent to the LLM; the rest stay on a local model</span>
          </div>
          <div className="card stat">
            <b>{HEADLINE.costPerMonth}</b>
            <span>a month to run this demo on AWS</span>
          </div>
        </div>
      </section>

      <div className="section-title" id="samples">
        <h2>Try it</h2>
        <span className="muted small">Synthetic documents only: never upload real patient data.</span>
      </div>
      <div className="samples">
        {samples.map((s) => {
          const info = describeSample(s.name)
          return (
            <button key={s.name} className="sample" disabled={busy} onClick={() => onSample(s.url, s.name)}>
              <h3>{info.title}</h3>
              <div className="tags">
                <span className="chip chip-brand">{info.kind}</span>
                <span className="chip">{info.scanned ? 'Scanned' : 'Digital'}</span>
              </div>
              <span className="muted small">{info.scanned ? 'OCR, then extraction' : 'Text layer, then extraction'}</span>
            </button>
          )
        })}
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
          <b>Upload your own</b>
          <span className="muted small">PDF or image · 5 MB · up to 5 pages</span>
        </label>
      </div>

      {busy && (
        <div className="card busy" role="status">
          <span className="spinner" />
          {slow
            ? 'Waking the server up: the first request after a quiet spell can take a minute or two.'
            : 'Reading the document…'}
        </div>
      )}
      {error && (
        <p className="error-box" role="alert">
          {error}
        </p>
      )}

      <div className="trust">
        <div className="card">
          <h3>Nothing is stored</h3>
          <p className="muted small">A document is read, answered and forgotten. Review happens in your browser.</p>
        </div>
        <div className="card">
          <h3>A human has the last word</h3>
          <p className="muted small">Uncertain fields are flagged, codes are suggestions, and the export records what you confirmed.</p>
        </div>
        <div className="card">
          <h3>Standard output</h3>
          <p className="muted small">LOINC for tests, ICD-10-CM for diagnoses, FHIR R4 for the record.</p>
        </div>
      </div>
    </>
  )
}
