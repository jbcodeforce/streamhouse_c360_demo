import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { ApiError } from '../api/client'
import { getC360Analytics, getCustomerProfile, getCustomerProfileRtce } from '../api/analytics'
import { searchCustomersByName } from '../api/customers'
import { formatCurrency, formatMs, nf } from '../lib/format'
import CustomerLookup from '../components/CustomerLookup'
import type { DataAnalytics, CategoryCount, CategoryValue } from '../types/analytics'

interface Bar {
  label: string
  /** Numeric magnitude that sizes the bar. */
  value: number
  /** Text shown at the end of the bar (count or formatted currency). */
  display: string
}

function BarChart({ title, bars }: { title: string; bars: Bar[] }) {
  const max = bars.reduce((m, b) => Math.max(m, b.value), 0)
  return (
    <figure className="chart-card">
      <figcaption className="chart-card__title">{title}</figcaption>
      {bars.length === 0 ? (
        <div className="status-msg">No data.</div>
      ) : (
        <ul className="bars">
          {bars.map((b) => (
            <li key={b.label} className="bar" title={`${b.label}: ${b.display}`}>
              <span className="bar__label">{b.label}</span>
              <span className="bar__track">
                <span
                  className="bar__fill"
                  style={{ width: max > 0 ? `${Math.max((b.value / max) * 100, 2)}%` : '0%' }}
                />
              </span>
              <span className="bar__value">{b.display}</span>
            </li>
          ))}
        </ul>
      )}
    </figure>
  )
}

function countBars(items: CategoryCount[]): Bar[] {
  return items.map((c) => ({ label: c.label, value: c.count, display: nf.format(c.count) }))
}

function valueBars(items: CategoryValue[]): Bar[] {
  return items.map((c) => ({ label: c.label, value: c.value, display: formatCurrency(c.value) }))
}

function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="stat-tile">
      <div className="stat-tile__value">{value}</div>
      <div className="stat-tile__label">{label}</div>
      {sub && <div className="stat-tile__sub">{sub}</div>}
    </div>
  )
}

export default function AnalyticsPage() {
  const [data, setData] = useState<DataAnalytics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setData(await getC360Analytics())
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load analytics')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const generatedAt = data ? new Date(data.generated_at).toLocaleString() : null

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Data Analytics</h1>
          <p className="page-subtitle">
            Snapshot of the <code>fct_c360_profile</code>, <code>fct_crm_summary</code>...  materialized tables served by the
            real-time context engine or snapshot query.
          </p>
          <a className="page-subtitle" href="/data-products">View Current Data Products</a>
        </div>
        <button className="btn btn--secondary btn--icon" onClick={() => void load()} disabled={loading}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <CustomerLookup
        title="Customer lookup via Flink snapshot query"
        badge="Flink Statements API"
        subtitle={
          <>
            Resolve the name against the operational customer service (system of record), then
            fetch the profile with a <code>WHERE customer_id = …</code> snapshot query (reads the
            upsert changelog and collapses it to current state).
          </>
        }
        search={searchCustomersByName}
        getProfile={getCustomerProfile}
      />

      <section className="profile-dashboard">
        <h2 className="profile-dashboard__title">
          <code>fct_c360_profile</code> — profile overview
        </h2>

        {data && (
          <div className="analytics-meta">
            <span className={`source-pill source-pill--${data.source_mode}`}>
              {data.source_mode === 'live' ? 'Live snapshot' : 'Mock snapshot'}
            </span>
            <span className="query-timer" title="Backend-measured snapshot query time">
              ⏱ Snapshot query {formatMs(data.query_ms)}
            </span>
            {generatedAt && <span className="analytics-meta__ts">Generated {generatedAt}</span>}
          </div>
        )}

        {loading && <div className="status-msg">Loading…</div>}
        {error && <div className="status-msg status-msg--error">{error}</div>}

      {!loading && !error && data && data.row_count === 0 && (
        <div className="status-msg">
          No profile rows in this snapshot. Confirm the Flink snapshot query is
          configured with Flink catalog/database credentials.
        </div>
      )}

      {!loading && !error && data && data.row_count > 0 && (
        <>
          <div className="stat-grid">
            <StatTile label="Customers" value={nf.format(data.total_customers)} />
            <StatTile label="Accounts" value={nf.format(data.total_accounts)} />
            <StatTile label="Total balance" value={formatCurrency(data.total_balance)} />
            <StatTile label="Transactions" value={nf.format(data.total_transactions)} />
            <StatTile
              label="Avg balance / customer"
              value={data.avg_balance_per_customer != null ? formatCurrency(data.avg_balance_per_customer) : '—'}
            />
            <StatTile label="Avg age" value={data.avg_age != null ? `${data.avg_age} yrs` : '—'} />
          </div>

          <div className="chart-grid">
            <BarChart title="Customers by segment" bars={countBars(data.by_segment)} />
            <BarChart title="Customers by generation" bars={countBars(data.by_generation)} />
            <BarChart title="Balance by segment" bars={valueBars(data.balance_by_segment)} />
            <BarChart title="Customers by country" bars={countBars(data.by_country)} />
            <BarChart title="Customers by gender" bars={countBars(data.by_gender)} />

            <figure className="chart-card">
              <figcaption className="chart-card__title">Profile completeness</figcaption>
              <dl className="dq-rows">
                <div className="dq-row">
                  <dt>Complete profiles</dt>
                  <dd>{nf.format(data.data_quality.complete)}</dd>
                </div>
                <div className="dq-row">
                  <dt>Missing email</dt>
                  <dd>{nf.format(data.data_quality.missing_email)}</dd>
                </div>
                <div className="dq-row">
                  <dt>Missing phone</dt>
                  <dd>{nf.format(data.data_quality.missing_phone)}</dd>
                </div>
              </dl>
            </figure>
          </div>
        </>
      )}
      </section>

      <CustomerLookup
        title="Customer lookup via RTCE"
        badge="Lightning Query API"
        subtitle={
          <>
            Same name resolution via the customer service, but the profile is served by the
            Real-Time Context Engine over the <code>fct_c360_profile</code> lightning table — a
            millisecond point lookup that returns current state directly (no changelog to collapse).
          </>
        }
        search={searchCustomersByName}
        getProfile={getCustomerProfileRtce}
      />
    </div>
  )
}
