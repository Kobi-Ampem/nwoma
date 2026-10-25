import { CODING, EXTRACTION, HEADLINE } from '../data'

const STEPS = [
  { title: 'Read', text: 'PDF text layer per page, Tesseract OCR (English + French) for scanned pages.' },
  { title: 'Classify', text: 'Lab report or referral letter, from the words on the page.' },
  { title: 'Extract', text: 'A fine-tuned multilingual model tags every field locally, in ~0.15 s.' },
  { title: 'Validate', text: 'Code checks catch what confidence misses: a flag the value contradicts, an impossible date.' },
  { title: 'Fall back', text: 'Only documents the validator objects to go to Gemini; the better answer is kept.' },
  { title: 'Code & export', text: 'LOINC and ICD-10-CM suggestions, human review, FHIR R4 with Provenance.' },
]

export function How() {
  return (
    <>
      <p className="eyebrow">How it works</p>
      <h1 style={{ fontSize: 34, margin: '6px 0 10px' }}>A local model first, an LLM only when it is needed</h1>
      <p className="muted" style={{ maxWidth: '72ch', fontSize: 17 }}>
        Every number below is measured on held-out synthetic documents the models never trained on: 300 lab reports and
        200 referral letters, half scanned, half in French, including layouts no model had seen.
      </p>

      <div className="stat-tiles">
        <div className="card stat"><b>{HEADLINE.cascadeF1}</b><span>field accuracy (F1) on 500 held-out documents</span></div>
        <div className="card stat"><b>{HEADLINE.fullyCorrect}</b><span>of documents with every field right</span></div>
        <div className="card stat"><b>{HEADLINE.toLlm}</b><span>sent to the LLM; the rest stay on the local model</span></div>
        <div className="card stat"><b>{HEADLINE.costPerMonth}</b><span>a month to run this demo on AWS</span></div>
      </div>

      <div className="section-title"><h2>The pipeline</h2></div>
      <div className="pipeline">
        {STEPS.map((s) => (
          <div key={s.title} className="card">
            <h3>{s.title}</h3>
            <p>{s.text}</p>
          </div>
        ))}
      </div>

      <div className="section-title">
        <h2>Extraction</h2>
        <span className="muted small">500 documents · F1 over every field</span>
      </div>
      <div className="card table-wrap">
        <table className="results-table">
          <thead><tr><th>System</th><th>F1</th><th>Documents fully correct</th><th>Sent to the LLM</th><th>Seconds per document</th></tr></thead>
          <tbody>
            {EXTRACTION.map((r) => (
              <tr key={r.system} className={r.best ? 'best' : ''}>
                <td>{r.system}</td><td className="num">{r.f1}</td><td className="num">{r.correct}</td><td className="num">{r.llm}</td><td className="num">{r.seconds}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        The cascade matches the LLM's accuracy with a third of the calls, and gets more documents fully right than either
        extractor alone, because each wins on different documents.
      </p>

      <div className="section-title"><h2>Coding</h2><span className="muted small">top-1: first suggestion right · top-5: right code among the five shown</span></div>
      <div className="card table-wrap">
        <table className="results-table">
          <thead><tr><th>Task</th><th>Top-1</th><th>Top-5</th><th /></tr></thead>
          <tbody>
            {CODING.map((r) => (
              <tr key={r.task}><td>{r.task}</td><td className="num">{r.top1}</td><td className="num">{r.top5}</td><td className="muted small">{r.note}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="two-col" style={{ marginTop: 28 }}>
        <section className="card card-pad prose">
          <h2 style={{ fontSize: 18, marginBottom: 10 }}>Architecture and cost</h2>
          <p>One AWS Lambda container behind a function URL, deployed from GitHub Actions without stored keys. The review screen is this static site.</p>
          <ul>
            <li>Nwoma stores nothing: documents are read, answered and forgotten. Documents that fail a check are sent to Google's Gemini API, whose free tier may keep them, which is one reason the demo takes test documents only.</li>
            <li>About {HEADLINE.costPerMonth} a month, with a budget alarm that switches the API off at $1.99.</li>
            <li>An MCP server offers the same tools to AI assistants.</li>
          </ul>
        </section>
        <section className="card card-pad prose">
          <h2 style={{ fontSize: 18, marginBottom: 10 }}>Known limits</h2>
          <ul>
            <li>The local model learns column order: on an unseen layout that reorders columns it drops sharply, so the cascade routes those to the LLM.</li>
            <li>OCR can drop the first line inside a bordered box; required fields that go missing are flagged for review.</li>
            <li>Code suggestions are right first time about half the time, so a person chooses from five.</li>
            <li>Synthetic data only: real documents would score lower.</li>
          </ul>
        </section>
      </div>
      <p style={{ marginTop: 24 }}>
        <a className="btn" href="https://github.com/Kobi-Ampem/nwoma">Source, decisions and evaluations on GitHub</a>
      </p>
    </>
  )
}
