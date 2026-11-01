import { useCallback, useEffect, useState } from 'react'

type Dependency = { status: 'up' | 'down'; detail: string | null }
type Health = { status: string; version: string }
type Readiness = { status: 'ready' | 'not_ready'; dependencies: Record<string, Dependency> }
type LoadState = 'loading' | 'connected' | 'disconnected'

function isHealth(value: unknown): value is Health {
  return typeof value === 'object' && value !== null &&
    'status' in value && value.status === 'ok' &&
    'version' in value && typeof value.version === 'string'
}

function isReadiness(value: unknown): value is Readiness {
  if (typeof value !== 'object' || value === null || !('status' in value) || !('dependencies' in value)) {
    return false
  }
  if (value.status !== 'ready' && value.status !== 'not_ready') return false
  if (typeof value.dependencies !== 'object' || value.dependencies === null) return false
  const dependencies = value.dependencies as Record<string, unknown>
  return ['postgres', 'redis', 'minio'].every((name) => name in dependencies) &&
    Object.values(dependencies).every((dependency) =>
    typeof dependency === 'object' && dependency !== null &&
    'status' in dependency && (dependency.status === 'up' || dependency.status === 'down') &&
    'detail' in dependency && (dependency.detail === null || typeof dependency.detail === 'string'),
    )
}

const dependencyNames: Record<string, string> = {
  postgres: 'PostgreSQL',
  redis: 'Redis',
  minio: 'MinIO object storage',
}

export default function App() {
  const [state, setState] = useState<LoadState>('loading')
  const [health, setHealth] = useState<Health | null>(null)
  const [readiness, setReadiness] = useState<Readiness | null>(null)
  const [checkedAt, setCheckedAt] = useState<Date | null>(null)

  const refresh = useCallback(async () => {
    setState('loading')
    try {
      const [healthResponse, readyResponse] = await Promise.all([
        fetch('/api/health', { headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(5_000) }),
        fetch('/api/ready', { headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(5_000) }),
      ])
      if (!healthResponse.ok || ![200, 503].includes(readyResponse.status)) {
        throw new Error(`Unexpected API response: health ${healthResponse.status}, readiness ${readyResponse.status}`)
      }
      const healthBody: unknown = await healthResponse.json()
      const readyBody: unknown = await readyResponse.json()
      if (!isHealth(healthBody) || !isReadiness(readyBody)) throw new Error('API response did not match the expected health contract')
      setHealth(healthBody)
      setReadiness(readyBody)
      setCheckedAt(new Date())
      setState('connected')
    } catch {
      setHealth(null)
      setReadiness(null)
      setCheckedAt(new Date())
      setState('disconnected')
    }
  }, [])

  useEffect(() => {
    void refresh()
    const interval = window.setInterval(() => void refresh(), 10_000)
    return () => window.clearInterval(interval)
  }, [refresh])

  const apiReady = readiness?.status === 'ready'

  return (
    <main className="page-shell">
      <header className="topbar">
        <a className="brand" href="#home" aria-label="Data Optimizer home">
          <span className="brand-mark" aria-hidden="true">DO</span>
          <span>Data Optimizer</span>
        </a>
        <span className="environment-tag"><span className="tag-dot" /> Local workspace</span>
      </header>

      <section className="hero" aria-labelledby="page-title">
        <div className="eyebrow"><span className="eyebrow-line" /> Evidence before recommendations</div>
        <h1 id="page-title">Make your data work<br /><em>smarter.</em></h1>
        <p className="hero-copy">
          Compare storage choices against your data and workload. Every recommendation starts with
          measured evidence and keeps unknowns visible.
        </p>

        <section className={`connection-card ${state}`} aria-label="Backend connectivity" aria-live="polite">
          <div className="connection-heading">
            <span className={`connection-icon ${state}`} aria-hidden="true">
              {state === 'connected' ? '✓' : state === 'disconnected' ? '!' : '…'}
            </span>
            <div>
              <h2>
                {state === 'loading' && 'Connecting to the API'}
                {state === 'connected' && 'API connection established'}
                {state === 'disconnected' && 'API is not reachable'}
              </h2>
              <p>
                {state === 'loading' && 'Checking the local service now.'}
                {state === 'connected' && `Service version ${health?.version ?? 'unknown'}`}
                {state === 'disconnected' && 'Start the API process, then retry this check.'}
              </p>
            </div>
            <button className="refresh-button" onClick={() => void refresh()} disabled={state === 'loading'}>
              {state === 'loading' ? 'Checking…' : 'Check again'}
            </button>
          </div>

          {state === 'connected' && readiness && (
            <div className="readiness-panel">
              <div className={`readiness-summary ${apiReady ? 'ready' : 'not-ready'}`}>
                <span className="summary-dot" />
                <span>{apiReady ? 'Dependencies ready' : 'Dependencies need attention'}</span>
              </div>
              <ul className="dependency-list">
                {Object.entries(readiness.dependencies).map(([key, dependency]) => (
                  <li key={key}>
                    <span className={`status-dot ${dependency.status}`} />
                    <span className="dependency-name">{dependencyNames[key] ?? key}</span>
                    <span className={`dependency-status ${dependency.status}`}>
                      {dependency.status === 'up' ? 'Connected' : dependency.detail ?? 'Unavailable'}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {state === 'disconnected' && (
            <div className="connection-help">
              <span className="help-mark" aria-hidden="true">i</span>
              <span>Run <code>make dev</code> from the project directory to start the API and dashboard.</span>
            </div>
          )}
          <div className="connection-footer">
            <span>{checkedAt ? `Last checked ${checkedAt.toLocaleTimeString()}` : 'Awaiting first check'}</span>
            <span className="live-indicator"><span /> Auto checks every 10 seconds</span>
          </div>
        </section>
      </section>

      <section className="principles" aria-label="Product principles">
        <article><span className="principle-number">01</span><h3>Use your evidence</h3><p>Recommendations follow the actual data shape and access patterns.</p></article>
        <article><span className="principle-number">02</span><h3>Keep uncertainty clear</h3><p>Unknown costs and requirements stay unknown until measured.</p></article>
        <article><span className="principle-number">03</span><h3>Preserve your original</h3><p>Compare verified copies while keeping the current setup in view.</p></article>
      </section>

      <footer className="page-footer"><span>DATA OPTIMIZER <span className="footer-separator">/</span> LOCAL DEVELOPMENT</span><span>Assessment workflows are introduced in later sprints.</span></footer>
    </main>
  )
}
