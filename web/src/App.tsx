import { useEffect, useMemo, useState } from 'react'
import {
  API_URL,
  type CodeSuggestion,
  type ExtractResponse,
  type Extraction,
  extract,
  sampleFile,
  samples as listSamples,
  toFhir,
} from './api'
import { type FieldRow, fieldRows, locate, setField } from './review'

// Lab results and diagnoses carry a code; the code lives with the result or diagnosis group.
function codeKey(path: string): string | null {
  const m = /^(results|diagnoses)\[(\d+)\]/.exec(path)
  return m ? `${m[1]}[${m[2]}]` : null
}

export default function App() {
  const [sampleList, setSampleList] = useState<{ name: string; url: string }[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [response, setResponse] = useState<ExtractResponse | null>(null)
  const [ext, setExt] = useState<Extraction | null>(null)
  const [confirmed, setConfirmed] = useState<Set<string>>(new Set())
  const [codes, setCodes] = useState<Record<string, string>>({})
  const [reviewer, setReviewer] = useState('')
  const [active, setActive] = useState<string | null>(null)
  const [fileUrl, setFileUrl] = useState<string | null>(null)
  const [view, setView] = useState<'text' | 'pdf'>('text')

  useEffect(() => {
    listSamples().then(setSampleList).catch(() => setSampleList([]))
    // A shareable demo link: ?sample=lab-report-fr-scanned.pdf opens that sample directly.
    const sample = new URLSearchParams(window.location.search).get('sample')
    if (sample) sampleFile(`/samples/${encodeURIComponent(sample)}`).then((blob) => run(blob, sample))
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, on load
  }, [])

  async function run(file: Blob, name: string) {
    setBusy(true)
    setError(null)
    if (fileUrl) URL.revokeObjectURL(fileUrl)
    setFileUrl(URL.createObjectURL(file))
    try {
      const r = await extract(file, name)
      setResponse(r)
      setExt(r.extraction)
      setConfirmed(new Set())
      setCodes(Object.fromEntries(Object.entries(r.codes).map(([k, v]) => [k, v[0]?.code ?? ''])))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setResponse(null)
    } finally {
      setBusy(false)
    }
  }

  const rows = useMemo(() => (ext && response ? fieldRows(ext, response.doc_type) : []), [ext, response])
  const issues = useMemo(() => {
    const byPath = new Map<string, string>()
    response?.issues.forEach((i) => byPath.set(i.field, i.message))
    return byPath
  }, [response])

  function edit(path: string, value: string) {
    if (!ext) return
    setExt(setField(ext, path, value))
    setConfirmed((c) => new Set(c).add(path)) // editing a field is confirming it
  }

  function toggle(path: string) {
    setConfirmed((c) => {
      const next = new Set(c)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  async function exportFhir() {
    if (!response || !ext) return
    try {
      const bundle = await toFhir({
        doc_id: response.doc_id,
        doc_type: response.doc_type,
        extraction: ext,
        codes: Object.fromEntries(Object.entries(codes).filter(([, c]) => c)),
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
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const groups = useMemo(() => {
    const map = new Map<string, FieldRow[]>()
    rows.forEach((r) => map.set(r.group, [...(map.get(r.group) ?? []), r]))
    return [...map.entries()]
  }, [rows])

  return (
    <div className="page">
      <header>
        <h1>Nwoma</h1>
        <p className="tagline">
          Clinical documents in, coded and verified records out. Lab reports and referral letters, English
          or French, digital or scanned.
        </p>
      </header>

      <section className="intake">
        <label className="upload">
          <input
            type="file"
            accept="application/pdf,image/*"
            onChange={(e) => e.target.files?.[0] && run(e.target.files[0], e.target.files[0].name)}
          />
          <span>{busy ? 'Reading the document…' : 'Choose a PDF or image (5 MB max)'}</span>
        </label>
        {sampleList.length > 0 && (
          <div className="samples">
            <span>or try a synthetic sample:</span>
            {sampleList.map((s) => (
              <button
                key={s.name}
                disabled={busy}
                onClick={async () => run(await sampleFile(s.url), s.name)}
              >
                {s.name.replace('.pdf', '').replaceAll('-', ' ')}
              </button>
            ))}
          </div>
        )}
        <p className="note">
          Demo only: use synthetic documents, never real patient data. Nothing is stored. Nwoma transcribes; it
          does not diagnose.
        </p>
        {error && <p className="error">{error}</p>}
      </section>

      {response && ext && (
        <>
          <section className="status">
            <span>{response.doc_type === 'lab' ? 'Lab report' : 'Referral letter'}</span>
            <span>read by {response.text_source === 'ocr' ? 'OCR' : 'PDF text'}</span>
            <span>extracted by {response.extractor === 'ner' ? 'local model' : 'LLM fallback'}</span>
            <span>{response.seconds.toFixed(1)} s</span>
            <span className={response.issues.length ? 'warn' : 'ok'}>
              {response.issues.length
                ? `${response.issues.length} field${response.issues.length > 1 ? 's' : ''} to check`
                : 'no issues found'}
            </span>
            {response.notes.map((n) => (
              <span key={n} className="muted">
                {n}
              </span>
            ))}
          </section>

          <main className="workspace">
            <section className="document">
              <div className="tabs">
                <button className={view === 'text' ? 'on' : ''} onClick={() => setView('text')}>
                  Text with fields
                </button>
                <button className={view === 'pdf' ? 'on' : ''} onClick={() => setView('pdf')}>
                  Original
                </button>
              </div>
              {view === 'text' ? (
                <DocumentText text={response.text} rows={rows} issues={issues} confirmed={confirmed} active={active} />
              ) : (
                fileUrl && <iframe title="original document" src={fileUrl} />
              )}
            </section>

            <section className="review">
              {groups.map(([group, groupRows]) => {
                const key = codeKey(groupRows[0].path)
                const suggestions: CodeSuggestion[] = key ? (response.codes[key] ?? []) : []
                return (
                  <fieldset key={group}>
                    <legend>{group}</legend>
                    {groupRows.map((row) => (
                      <div
                        key={row.path}
                        className={`field ${issues.has(row.path) ? 'issue' : ''} ${confirmed.has(row.path) ? 'confirmed' : ''}`}
                      >
                        <label htmlFor={row.path}>{row.label}</label>
                        <input
                          id={row.path}
                          value={row.value}
                          onChange={(e) => edit(row.path, e.target.value)}
                          onFocus={() => setActive(row.path)}
                          onBlur={() => setActive(null)}
                        />
                        <button
                          className="tick"
                          title={confirmed.has(row.path) ? 'Confirmed' : 'Mark as checked'}
                          aria-pressed={confirmed.has(row.path)}
                          onClick={() => toggle(row.path)}
                        >
                          ✓
                        </button>
                        {issues.has(row.path) && <p className="message">{issues.get(row.path)}</p>}
                      </div>
                    ))}
                    {key && suggestions.length > 0 && (
                      <div className="field code">
                        <label htmlFor={`${key}-code`}>{key.startsWith('results') ? 'LOINC' : 'ICD-10-CM'}</label>
                        <select
                          id={`${key}-code`}
                          value={codes[key] ?? ''}
                          onChange={(e) => setCodes({ ...codes, [key]: e.target.value })}
                        >
                          {suggestions.map((s) => (
                            <option key={s.code} value={s.code}>
                              {s.code} · {s.display}
                            </option>
                          ))}
                          <option value="">no code</option>
                        </select>
                      </div>
                    )}
                  </fieldset>
                )
              })}

              <div className="export">
                <input placeholder="Reviewer name" value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
                <button className="primary" onClick={exportFhir}>
                  Download FHIR bundle
                </button>
                <p className="muted">
                  {confirmed.size} of {rows.length} fields confirmed. Confirmed fields are recorded as Provenance.
                </p>
              </div>
            </section>
          </main>
        </>
      )}

      <footer>
        Synthetic data only · <a href="https://github.com/Kobi-Ampem/nwoma">source on GitHub</a> · API {API_URL}
      </footer>
    </div>
  )
}

function DocumentText(props: {
  text: string
  rows: FieldRow[]
  issues: Map<string, string>
  confirmed: Set<string>
  active: string | null
}) {
  const { text, rows, issues, confirmed, active } = props
  const highlights = locate(text, rows)
  const parts: React.ReactNode[] = []
  let at = 0
  for (const h of highlights) {
    if (h.start > at) parts.push(text.slice(at, h.start))
    const state = h.path === active ? 'active' : issues.has(h.path) ? 'issue' : confirmed.has(h.path) ? 'confirmed' : 'found'
    parts.push(
      <mark key={h.start} className={state} title={h.path}>
        {text.slice(h.start, h.end)}
      </mark>,
    )
    at = h.end
  }
  parts.push(text.slice(at))
  return <pre className="text">{parts}</pre>
}
