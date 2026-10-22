import { useEffect, useMemo, useState } from 'react'
import { type FieldRow, locate } from '../review'

// pdf.js is large: it loads only when a document is opened, not with the home page.
async function renderPdf(file: Blob): Promise<string[]> {
  const [{ GlobalWorkerOptions, getDocument }, worker] = await Promise.all([
    import('pdfjs-dist'),
    import('pdfjs-dist/build/pdf.worker.min.mjs?url'),
  ])
  GlobalWorkerOptions.workerSrc = worker.default
  const pdf = await getDocument({ data: new Uint8Array(await file.arrayBuffer()) }).promise
  const pages: string[] = []
  for (let n = 1; n <= pdf.numPages; n++) {
    const page = await pdf.getPage(n)
    const viewport = page.getViewport({ scale: 1.6 })
    const canvas = document.createElement('canvas')
    canvas.width = viewport.width
    canvas.height = viewport.height
    await page.render({ canvas, viewport }).promise
    pages.push(canvas.toDataURL('image/png'))
  }
  return pages
}

// The original PDF, rendered by pdf.js onto canvases: no browser PDF toolbar or comment panel,
// and the same in every browser. Remounted per document (key), so it starts empty each time.
function PdfPages({ file }: { file: Blob }) {
  const [pages, setPages] = useState<string[] | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let cancelled = false
    renderPdf(file).then(
      (p) => !cancelled && setPages(p),
      () => !cancelled && setFailed(true),
    )
    return () => {
      cancelled = true
    }
  }, [file])
  if (failed) return <p className="muted">This document cannot be previewed, but its text was read.</p>
  if (!pages)
    return (
      <div className="busy">
        <span className="spinner" /> Rendering the document…
      </div>
    )
  return (
    <>
      {pages.map((src, i) => (
        <img key={i} className="page-canvas" src={src} alt={`Page ${i + 1} of the original document`} />
      ))}
    </>
  )
}

function ImagePage({ file }: { file: Blob }) {
  const url = useMemo(() => URL.createObjectURL(file), [file])
  useEffect(() => () => URL.revokeObjectURL(url), [url])
  return <img className="page-canvas" src={url} alt="The original document" />
}

function FieldText(props: {
  text: string
  rows: FieldRow[]
  issues: Map<string, string>
  confirmed: Set<string>
  active: string | null
}) {
  const { text, rows, issues, confirmed, active } = props
  const parts: React.ReactNode[] = []
  let at = 0
  for (const h of locate(text, rows)) {
    if (h.start > at) parts.push(text.slice(at, h.start))
    const state =
      h.path === active ? 'active' : issues.has(h.path) ? 'issue' : confirmed.has(h.path) ? 'confirmed' : ''
    parts.push(
      <mark key={h.start} className={state} title={h.path}>
        {text.slice(h.start, h.end)}
      </mark>,
    )
    at = h.end
  }
  parts.push(text.slice(at))
  return <pre className="doc-text">{parts}</pre>
}

export function DocumentViewer(props: {
  file: Blob
  fileKey: string
  isPdf: boolean
  text: string
  rows: FieldRow[]
  issues: Map<string, string>
  confirmed: Set<string>
  active: string | null
}) {
  const [view, setView] = useState<'original' | 'text'>('original')
  return (
    <section className="card viewer" aria-label="Document">
      <div className="viewer-tabs" role="tablist">
        <button role="tab" aria-selected={view === 'original'} className={view === 'original' ? 'on' : ''} onClick={() => setView('original')}>
          Original
        </button>
        <button role="tab" aria-selected={view === 'text'} className={view === 'text' ? 'on' : ''} onClick={() => setView('text')}>
          Text with fields
        </button>
      </div>
      <div className="viewer-body">
        {view === 'text' ? (
          <FieldText {...props} />
        ) : props.isPdf ? (
          <PdfPages key={props.fileKey} file={props.file} />
        ) : (
          <ImagePage file={props.file} />
        )}
      </div>
    </section>
  )
}
