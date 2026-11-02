import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { listScenarios, runScenario } from '../api/scenarios'
import type { ScenarioDefinition, ScenarioResult } from '../types/scenario'

// Map pattern name to a colour accent for the pattern card
function patternAccent(pattern: string): { border: string; dot: string; label: string } {
  if (pattern.includes('fraud'))    return { border: '#fca5a5', dot: '#dc2626', label: 'Fraud' }
  if (pattern.includes('smb'))      return { border: '#fcd34d', dot: '#d97706', label: 'Anomaly' }
  return                                   { border: '#86efac', dot: '#16a34a', label: 'Loyalty' }
}

export default function CEPPage() {
  const [scenarios, setScenarios] = useState<ScenarioDefinition[]>([])
  const [selected, setSelected] = useState<ScenarioDefinition | null>(null)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<ScenarioResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listScenarios()
      .then((s) => {
        setScenarios(s)
        if (s.length > 0) setSelected(s[0])
      })
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : 'Failed to load scenarios'))
      .finally(() => setLoading(false))
  }, [])

  function selectScenario(sc: ScenarioDefinition) {
    setSelected(sc)
    setResult(null)
    setError(null)
  }

  async function trigger() {
    if (!selected) return
    setRunning(true)
    setError(null)
    setResult(null)
    try {
      const res = await runScenario(selected.scenario_id)
      setResult(res)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to run scenario')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 style={{ margin: 0 }}>Complex Event Processing</h1>
          <p className="page-subtitle">
            Three <code>MATCH_RECOGNIZE</code> patterns — trigger a scenario and watch Flink
            detect the event sequence in real time.
          </p>
        </div>
      </div>

      {loading && <div className="status-msg">Loading scenarios…</div>}
      {loadError && <div className="status-msg status-msg--error">{loadError}</div>}

      {!loading && !loadError && (
        <>
          {/* Pattern cards */}
          <div className="cep-cards">
            {scenarios.map((sc) => {
              const accent = patternAccent(sc.pattern)
              const isActive = selected?.scenario_id === sc.scenario_id
              return (
                <button
                  key={sc.scenario_id}
                  className={`cep-card${isActive ? ' cep-card--active' : ''}`}
                  style={{ borderColor: isActive ? accent.border : undefined }}
                  onClick={() => selectScenario(sc)}
                >
                  <div className="cep-card__dot" style={{ background: accent.dot }} />
                  <div className="cep-card__body">
                    <div className="cep-card__label">{accent.label}</div>
                    <div className="cep-card__title">{sc.label}</div>
                    <div className="cep-card__pattern"><code>{sc.pattern}</code></div>
                  </div>
                </button>
              )
            })}
          </div>

          {/* Detail panel */}
          {selected && (
            <div className="cep-detail">
              <div className="cep-detail__head">
                <div>
                  <h2 className="cep-detail__title">{selected.label}</h2>
                  <p className="cep-detail__desc">{selected.description}</p>
                </div>
                <button
                  className="btn"
                  onClick={() => void trigger()}
                  disabled={running}
                  style={{ flexShrink: 0 }}
                >
                  {running ? 'Running…' : 'Trigger Scenario'}
                </button>
              </div>

              {error && <div className="status-msg status-msg--error">{error}</div>}

              {result && (
                <div className="cep-result">
                  <div className="cep-result__meta">
                    <span className="source-pill source-pill--live">injected</span>
                    <span className="analytics-meta__ts">
                      {new Date(result.triggered_at).toLocaleTimeString()} —{' '}
                      {result.transactions.length} transaction
                      {result.transactions.length !== 1 ? 's' : ''} written
                    </span>
                  </div>
                  <table className="table" style={{ marginTop: 12 }}>
                    <thead>
                      <tr>
                        <th>Type</th>
                        <th>Amount</th>
                        <th>Merchant</th>
                        <th>Category</th>
                        <th>Channel</th>
                        <th>Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.transactions.map((t) => (
                        <tr key={t.transaction_id}>
                          <td>
                            <span
                              className={`cep-type cep-type--${t.transaction_type.toLowerCase()}`}
                            >
                              {t.transaction_type}
                            </span>
                          </td>
                          <td style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
                            ${t.amount.toFixed(2)}
                          </td>
                          <td>{t.merchant_name ?? '—'}</td>
                          <td>{t.merchant_category ?? '—'}</td>
                          <td>{t.channel ?? '—'}</td>
                          <td style={{ fontVariantNumeric: 'tabular-nums' }}>
                            {t.transacted_at
                              ? new Date(t.transacted_at).toLocaleTimeString()
                              : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
