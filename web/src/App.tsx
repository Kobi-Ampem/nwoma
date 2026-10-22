import { useEffect, useState } from 'react'
import { API_URL, explain, extract, sampleFile, samples as listSamples } from './api'
import { Export } from './pages/Export'
import { Home } from './pages/Home'
import { How } from './pages/How'
import { Review } from './pages/Review'
import { Summary } from './pages/Summary'
import { type Session, startSession } from './session'

type Route = '' | 'review' | 'export' | 'summary' | 'how'

function useRoute(): Route {
  const read = () => (window.location.hash.replace(/^#\/?/, '').split('?')[0] as Route) || ''
  const [route, setRoute] = useState<Route>(read)
  useEffect(() => {
    const onChange = () => {
      setRoute(read())
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

export default function App() {
  const route = useRoute()
  const [sampleList, setSampleList] = useState<{ name: string; url: string }[]>([])
  const [session, setSession] = useState<Session | null>(null)
  const [reviewer, setReviewer] = useState('')
  const [busy, setBusy] = useState(false)
  const [slow, setSlow] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(file: Blob, name: string) {
    setBusy(true)
    setSlow(false)
    setError(null)
    const timer = window.setTimeout(() => setSlow(true), 5000) // the API sleeps when idle
    try {
      const response = await extract(file, name)
      setSession(startSession(response, file, name))
      window.location.hash = '#/review'
    } catch (e) {
      setError(explain(e))
    } finally {
      window.clearTimeout(timer)
      setBusy(false)
    }
  }

  async function runSample(url: string, name: string) {
    try {
      run(await sampleFile(url), name)
    } catch (e) {
      setError(explain(e))
    }
  }

  useEffect(() => {
    listSamples().then(setSampleList).catch(() => setSampleList([]))
    // A shareable demo link: ?sample=lab-report-fr-scanned.pdf opens that sample directly.
    const sample = new URLSearchParams(window.location.search).get('sample')
    if (sample) runSample(`/samples/${encodeURIComponent(sample)}`, sample)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, on load
  }, [])

  const needsDoc = (route === 'review' || route === 'export' || route === 'summary') && !session
  const page = needsDoc || route === '' ? 'home' : route
  const update = (change: (s: Session) => Session) => setSession((s) => (s ? change(s) : s))

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="#/">
            <b>Nwoma</b>
            <small>clinical document extraction</small>
          </a>
          <nav className="nav">
            <a className={page === 'home' ? 'on' : ''} href="#/">Home</a>
            {session && <a className={page === 'review' || page === 'export' || page === 'summary' ? 'on' : ''} href="#/review">Review</a>}
            <a className={page === 'how' ? 'on' : ''} href="#/how">How it works</a>
          </nav>
        </div>
      </header>
      <main className="page">
        {page === 'home' && <Home samples={sampleList} busy={busy} slow={slow} error={error} onFile={run} onSample={runSample} />}
        {page === 'review' && session && <Review session={session} update={update} />}
        {page === 'export' && session && <Export session={session} reviewer={reviewer} setReviewer={setReviewer} />}
        {page === 'summary' && session && <Summary session={session} reviewer={reviewer} />}
        {page === 'how' && <How />}
      </main>
      <footer className="footer">
        <span>Synthetic data only · transcription, not diagnosis</span>
        <a href="https://github.com/Kobi-Ampem/nwoma">GitHub</a>
        <span>API {API_URL.replace(/^https?:\/\//, '').slice(0, 32)}…</span>
      </footer>
    </>
  )
}
