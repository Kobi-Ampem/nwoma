import { useEffect, useMemo, useRef, useState } from 'react'
import { type CodeSuggestion, suggestCodes } from '../api'
import { DocumentViewer } from '../components/DocumentViewer'
import { ExportPanel } from '../components/ExportPanel'
import { HEADER_FIELDS, allPaths, codeKeyAffectedBy, fieldRows, itemPaths, setField } from '../review'
import type { Session } from '../session'

type Update = (change: (s: Session) => Session) => void

function Tick(props: { on: boolean; label: string; onClick: () => void }) {
  return (
    <button className="tick" aria-pressed={props.on} title={props.on ? `${props.label}: confirmed` : `Confirm ${props.label}`} onClick={props.onClick}>
      ✓
    </button>
  )
}

function CodeSelect(props: {
  id: string
  value: string
  confirmed: boolean
  suggestions: CodeSuggestion[]
  onChange: (code: string) => void
}) {
  return (
    <select
      id={props.id}
      className={`code-select ${props.confirmed ? '' : 'unconfirmed'}`}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
      title={props.confirmed ? 'Code confirmed' : 'Suggested code: confirm the row to accept it'}
    >
      {props.suggestions.map((s) => (
        <option key={s.code} value={s.code}>
          {s.code} · {s.display}
        </option>
      ))}
      <option value="">no code</option>
    </select>
  )
}

export function Review(props: { session: Session; update: Update; reviewer: string; setReviewer: (name: string) => void }) {
  const { session, update } = props
  const { response, ext, confirmed, codes, suggestions } = session
  const [active, setActive] = useState<string | null>(null)
  const timers = useRef<Record<string, number>>({})

  const rows = useMemo(() => fieldRows(ext, response.doc_type), [ext, response.doc_type])
  const issues = useMemo(() => new Map(response.issues.map((i) => [i.field, i.message])), [response.issues])
  const paths = useMemo(() => allPaths(ext, response.doc_type, codes), [ext, response.doc_type, codes])
  const done = paths.filter((p) => confirmed.has(p)).length

  useEffect(() => () => Object.values(timers.current).forEach((t) => window.clearTimeout(t)), [])

  // An edit to a test name, unit or diagnosis unconfirms its code and fetches fresh suggestions.
  function edit(path: string, value: string) {
    const key = codeKeyAffectedBy(path)
    update((s) => {
      const next = new Set(s.confirmed)
      next.add(path)
      if (key) next.delete(`${key}.code`)
      return { ...s, ext: setField(s.ext, path, value), confirmed: next }
    })
    if (!key) return
    window.clearTimeout(timers.current[key])
    timers.current[key] = window.setTimeout(async () => {
      const kind = key.startsWith('results') ? 'lab' : 'diagnosis'
      const target = key.startsWith('results')
        ? session.ext.results[Number(key.match(/\d+/)![0])]
        : undefined
      const latest = path.endsWith('.unit') ? { name: target?.test_name ?? '', unit: value } : { name: value, unit: target?.unit ?? null }
      try {
        const fresh = await suggestCodes(kind, latest.name, kind === 'lab' ? latest.unit : null)
        update((s) => ({
          ...s,
          suggestions: { ...s.suggestions, [key]: fresh },
          codes: { ...s.codes, [key]: fresh[0]?.code ?? '' },
        }))
      } catch {
        // Suggestions stay as they were; the code is still unconfirmed, so nothing is exported as checked.
      }
    }, 600)
  }

  function toggle(itemKey: string) {
    const itemP = itemPaths(itemKey, Boolean(codes[itemKey]))
    update((s) => {
      const next = new Set(s.confirmed)
      const all = itemP.every((p) => next.has(p))
      itemP.forEach((p) => (all ? next.delete(p) : next.add(p)))
      return { ...s, confirmed: next }
    })
  }

  function chooseCode(key: string, code: string) {
    // Choosing a code is a deliberate act: it counts as confirming that code.
    update((s) => {
      const next = new Set(s.confirmed)
      if (code) next.add(`${key}.code`)
      else next.delete(`${key}.code`)
      return { ...s, codes: { ...s.codes, [key]: code }, confirmed: next }
    })
  }

  // Confirms every field and code except those in a row or field the validator flagged.
  function confirmUnflagged() {
    const flagged = (p: string) => {
      const item = p.match(/^\w+\[\d+\]/)?.[0]
      return item ? [...issues.keys()].some((k) => k === item || k.startsWith(`${item}.`)) : issues.has(p)
    }
    update((s) => ({ ...s, confirmed: new Set([...s.confirmed, ...paths.filter((p) => !flagged(p))]) }))
  }

  function jump(path: string) {
    const el = document.getElementById(path)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el?.focus()
  }

  const rowIssues = (key: string) => [...issues.entries()].filter(([p]) => p.startsWith(`${key}.`) || p === key)
  const isRowConfirmed = (key: string) => itemPaths(key, Boolean(codes[key])).every((p) => confirmed.has(p))
  const headerFields = HEADER_FIELDS.filter((f) => f.types.includes(response.doc_type))
  const focus = (path: string) => ({ onFocus: () => setActive(path), onBlur: () => setActive(null) })

  return (
    <>
      <div className="review-head">
        <div>
          <h1>{response.doc_type === 'lab' ? 'Lab report' : 'Referral letter'}</h1>
          <div className="meta" style={{ marginTop: 8 }}>
            <span className="chip">{session.fileName}</span>
            <span className="chip">Read by {response.text_source === 'ocr' ? 'OCR' : 'PDF text'}</span>
            <span className="chip">{response.extractor === 'ner' ? 'Local model' : 'LLM fallback'}</span>
            <span className="chip">{response.seconds.toFixed(1)} s</span>
          </div>
        </div>
        <a className="btn btn-ghost" href="#/">
          ← New document
        </a>
      </div>

      {response.issues.length > 0 ? (
        <div className="callout" role="status">
          <span aria-hidden>⚠</span>
          <div>
            <b>
              {response.issues.length} field{response.issues.length > 1 ? 's' : ''} need attention
            </b>
            <ul>
              {response.issues.map((i) => (
                <li key={i.field + i.kind}>
                  <button onClick={() => jump(i.field)}>{i.message}</button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : (
        <div className="callout callout-ok" role="status">
          <span aria-hidden>✓</span>
          <div>
            <b>No issues found.</b> Check the fields against the original and confirm them.
          </div>
        </div>
      )}
      {response.notes.map((n) => (
        <p key={n} className="muted small">
          {n}
        </p>
      ))}

      <div className="workspace">
        <DocumentViewer
          file={session.file}
          fileKey={response.doc_id}
          isPdf={session.isPdf}
          text={response.text}
          rows={rows}
          issues={issues}
          confirmed={confirmed}
          active={active}
        />

        <div className="panel">
          <section className="card">
            <header>
              <h2>Patient and document</h2>
            </header>
            <div className="fields">
              {headerFields.map((f) => {
                const path = f.key as string
                const value = (ext[f.key] as string | null) ?? ''
                return (
                  <div
                    key={path}
                    className={`field ${f.key === 'reason' ? 'wide' : ''} ${issues.has(path) ? 'issue-field' : ''} ${confirmed.has(path) ? 'confirmed-field' : ''}`}
                  >
                    <label htmlFor={path}>{f.label}</label>
                    <div className="field-row">
                      <input id={path} className="input" value={value} onChange={(e) => edit(path, e.target.value)} {...focus(path)} />
                      <Tick on={confirmed.has(path)} label={f.label} onClick={() => toggle(path)} />
                    </div>
                    {issues.has(path) && <span className="hint">{issues.get(path)}</span>}
                  </div>
                )
              })}
            </div>
          </section>

          {response.doc_type === 'lab' && (
            <section className="card">
              <header>
                <h2>Results</h2>
                <span className="muted small">{ext.results.length} tests · LOINC codes are suggestions</span>
              </header>
              <div className="table-wrap">
                <table className="grid">
                  <thead>
                    <tr>
                      <th>Test</th>
                      <th>Value</th>
                      <th>Unit</th>
                      <th>Range</th>
                      <th>Flag</th>
                      <th>LOINC</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {ext.results.flatMap((r, i) => {
                      const key = `results[${i}]`
                      const problems = rowIssues(key)
                      const cls = `${problems.length ? 'issue' : ''} ${isRowConfirmed(key) ? 'confirmed' : ''}`
                      const cell = (f: 'test_name' | 'value' | 'unit' | 'ref_range' | 'flag', width = '') => (
                        <td className={width}>
                          <input id={`${key}.${f}`} className="cell" value={r[f] ?? ''} aria-label={`${r.test_name} ${f}`}
                            onChange={(e) => edit(`${key}.${f}`, e.target.value)} {...focus(`${key}.${f}`)} />
                        </td>
                      )
                      const out = [
                        <tr key={key} className={cls}>
                          {cell('test_name', 'w-name')}
                          {cell('value', 'w-value')}
                          {cell('unit', 'w-unit')}
                          {cell('ref_range', 'w-range')}
                          {cell('flag', 'w-flag')}
                          <td>
                            <CodeSelect id={`${key}.code`} value={codes[key] ?? ''} confirmed={confirmed.has(`${key}.code`)}
                              suggestions={suggestions[key] ?? []} onChange={(c) => chooseCode(key, c)} />
                          </td>
                          <td>
                            <Tick on={isRowConfirmed(key)} label={r.test_name} onClick={() => toggle(key)} />
                          </td>
                        </tr>,
                      ]
                      if (problems.length)
                        out.push(
                          <tr key={`${key}-msg`} className="issue-msg">
                            <td colSpan={7}>{problems.map(([, m]) => m).join(' · ')}</td>
                          </tr>,
                        )
                      return out
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {response.doc_type === 'referral' && (
            <>
              <section className="card">
                <header>
                  <h2>Diagnoses</h2>
                  <span className="muted small">ICD-10-CM codes are suggestions</span>
                </header>
                {ext.diagnoses.length === 0 ? (
                  <p className="empty">No diagnoses found.</p>
                ) : (
                  <div className="table-wrap">
                    <table className="grid">
                      <tbody>
                        {ext.diagnoses.map((d, i) => {
                          const key = `diagnoses[${i}]`
                          return (
                            <tr key={key} className={isRowConfirmed(key) ? 'confirmed' : ''}>
                              <td>
                                <input id={key} className="cell" value={d} aria-label={`Diagnosis ${i + 1}`}
                                  onChange={(e) => edit(key, e.target.value)} {...focus(key)} />
                              </td>
                              <td>
                                <CodeSelect id={`${key}.code`} value={codes[key] ?? ''} confirmed={confirmed.has(`${key}.code`)}
                                  suggestions={suggestions[key] ?? []} onChange={(c) => chooseCode(key, c)} />
                              </td>
                              <td style={{ width: 48 }}>
                                <Tick on={isRowConfirmed(key)} label={d} onClick={() => toggle(key)} />
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <section className="card">
                <header>
                  <h2>Medications</h2>
                </header>
                {ext.medications.length === 0 ? (
                  <p className="empty">No current medications listed.</p>
                ) : (
                  <div className="table-wrap">
                    <table className="grid">
                      <thead>
                        <tr>
                          <th>Medication</th>
                          <th>Dose</th>
                          <th>Frequency</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {ext.medications.map((m, i) => {
                          const key = `medications[${i}]`
                          const cell = (f: 'name' | 'dose' | 'frequency') => (
                            <td>
                              <input id={`${key}.${f}`} className="cell" value={m[f] ?? ''} aria-label={`${m.name} ${f}`}
                                onChange={(e) => edit(`${key}.${f}`, e.target.value)} {...focus(`${key}.${f}`)} />
                            </td>
                          )
                          return (
                            <tr key={key} className={`${rowIssues(key).length ? 'issue' : ''} ${isRowConfirmed(key) ? 'confirmed' : ''}`}>
                              {cell('name')}
                              {cell('dose')}
                              {cell('frequency')}
                              <td style={{ width: 48 }}>
                                <Tick on={isRowConfirmed(key)} label={m.name} onClick={() => toggle(key)} />
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <section className="card">
                <header>
                  <h2>Allergies</h2>
                </header>
                {ext.allergies.length === 0 ? (
                  <p className="empty">No allergies listed.</p>
                ) : (
                  <div className="table-wrap">
                    <table className="grid">
                      <tbody>
                        {ext.allergies.map((a, i) => {
                          const key = `allergies[${i}]`
                          return (
                            <tr key={key} className={isRowConfirmed(key) ? 'confirmed' : ''}>
                              <td>
                                <input id={key} className="cell" value={a} aria-label={`Allergy ${i + 1}`}
                                  onChange={(e) => edit(key, e.target.value)} {...focus(key)} />
                              </td>
                              <td style={{ width: 48 }}>
                                <Tick on={isRowConfirmed(key)} label={a} onClick={() => toggle(key)} />
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}

          <div className="card actionbar">
            <div className="progress">
              <div className="progress-bar" aria-hidden>
                <span style={{ width: `${(100 * done) / Math.max(paths.length, 1)}%` }} />
              </div>
              <span className="small muted">
                {done} of {paths.length} confirmed
              </span>
            </div>
            <button className="btn btn-sm" onClick={confirmUnflagged}>
              Confirm all unflagged
            </button>
            <button className="btn btn-primary" onClick={() => document.getElementById('export')?.scrollIntoView({ behavior: 'smooth' })}>
              Export ↓
            </button>
          </div>
          <ExportPanel session={session} reviewer={props.reviewer} setReviewer={props.setReviewer} />
        </div>
      </div>
    </>
  )
}
