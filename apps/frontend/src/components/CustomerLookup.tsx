import { useState, type FormEvent, type ReactNode } from 'react'
import { Search } from 'lucide-react'
import { ApiError } from '../api/client'
import { formatCurrency, formatMs, nf } from '../lib/format'
import type { CustomerProfile } from '../types/analytics'
import type { Customer } from '../types/customer'

interface CustomerLookupProps {
  title: string
  subtitle: ReactNode
  /** Short engine label shown as a pill (e.g. "Flink snapshot", "RTCE"). */
  badge?: string
  /** Resolve a name to customers via the operational customer service. */
  search?: (name: string) => Promise<Customer[]>
  getProfile?: (customerId: string) => Promise<CustomerProfile>
  /**
   * Single-call alternative to `search` + `getProfile`: the backend resolves the
   * name in the database and returns the matching profiles directly.
   */
  searchProfiles?: (name: string) => Promise<CustomerProfile[]>
}

/** What the picker needs from a match (a Customer or a CustomerProfile). */
interface Match {
  customer_id: string
  first_name: string | null
  last_name: string | null
  segment?: string | null
  city?: string | null
  state?: string | null
}

function fullName(c: { first_name: string | null; last_name: string | null }): string {
  return [c.first_name, c.last_name].filter(Boolean).join(' ') || '(unnamed)'
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="profile-row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

function ProfileCard({ profile }: { profile: CustomerProfile }) {
  const location = [profile.city, profile.state, profile.country].filter(Boolean).join(', ') || '—'
  return (
    <div className="profile-card">
      <div className="profile-card__head">
        <h3>{fullName(profile)}</h3>
        {profile.customer_segment && (
          <span className="profile-seg">{profile.customer_segment}</span>
        )}
      </div>
      <code className="profile-card__id">customer_id = {profile.customer_id}</code>
      <div className="query-timer query-timer--card" title="Backend-measured lookup query time">
        ⏱ Lookup {formatMs(profile.query_ms)}
      </div>
      <dl className="profile-rows">
        <MetricRow label="Generation" value={profile.generation_segment ?? '—'} />
        <MetricRow label="Location" value={location} />
        <MetricRow label="Customer since" value={profile.customer_since ?? '—'} />
        <MetricRow
          label="Tenure"
          value={profile.days_since_registration != null ? `${nf.format(profile.days_since_registration)} days` : '—'}
        />
        <MetricRow label="Accounts" value={nf.format(profile.account_count)} />
        <MetricRow label="Total balance" value={formatCurrency(profile.total_balance)} />
        <MetricRow label="Transactions" value={nf.format(profile.txn_count)} />
        <MetricRow label="Transaction total" value={formatCurrency(profile.txn_total)} />
        <MetricRow label="Email on file" value={profile.missing_email_flag ? 'Missing' : 'Yes'} />
        <MetricRow label="Phone on file" value={profile.missing_phone_flag ? 'Missing' : 'Yes'} />
      </dl>
    </div>
  )
}

export default function CustomerLookup({
  title,
  subtitle,
  badge,
  search,
  getProfile,
  searchProfiles,
}: CustomerLookupProps) {
  const [query, setQuery] = useState('')
  const [matches, setMatches] = useState<Match[] | null>(null)
  const [loadedProfiles, setLoadedProfiles] = useState<CustomerProfile[]>([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [profile, setProfile] = useState<CustomerProfile | null>(null)
  const [profileLoading, setProfileLoading] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)

  async function selectCustomer(id: string) {
    setSelectedId(id)
    setProfile(null)
    setProfileError(null)
    setProfileLoading(true)
    try {
      const preloaded = loadedProfiles.find((p) => p.customer_id === id)
      if (preloaded) setProfile(preloaded)
      else if (getProfile) setProfile(await getProfile(id))
    } catch (e) {
      setProfileError(e instanceof ApiError ? e.message : 'Failed to load customer')
    } finally {
      setProfileLoading(false)
    }
  }

  async function onSearch(e: FormEvent) {
    e.preventDefault()
    const name = query.trim()
    setProfile(null)
    setProfileError(null)
    setSelectedId(null)
    if (!name) {
      setMatches(null)
      setSearchError(null)
      return
    }
    setSearching(true)
    setSearchError(null)
    try {
      if (searchProfiles) {
        const profiles = await searchProfiles(name)
        setLoadedProfiles(profiles)
        setMatches(
          profiles.map((p) => ({ ...p, segment: p.customer_segment })),
        )
        if (profiles.length === 1) {
          setSelectedId(profiles[0].customer_id)
          setProfile(profiles[0])
        }
      } else if (search) {
        const found = await search(name)
        setMatches(found)
        // One unambiguous hit → go straight to the WHERE customer_id = … query.
        if (found.length === 1) {
          await selectCustomer(found[0].customer_id)
        }
      }
    } catch (err) {
      setMatches(null)
      setSearchError(err instanceof ApiError ? err.message : 'Search failed')
    } finally {
      setSearching(false)
    }
  }

  return (
    <section className="lookup-card">
      <h2 className="lookup-card__title">
        {title}
        {badge && <span className="lookup-badge">{badge}</span>}
      </h2>
      <p className="lookup-card__sub">{subtitle}</p>

      <form className="lookup-form" onSubmit={onSearch}>
        <label className="lookup-form__field">
          <span className="lookup-form__label">Customer name</span>
          <input
            type="text"
            placeholder="e.g. Carter"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <button type="submit" className="btn btn--icon" disabled={searching}>
          <Search size={14} /> Search
        </button>
      </form>

      {searchError && <div className="status-msg status-msg--error">{searchError}</div>}
      {searching && <div className="status-msg">Searching…</div>}

      {!searching && matches !== null && matches.length === 0 && (
        <div className="status-msg">No customers match “{query.trim()}”.</div>
      )}

      {!searching && matches !== null && matches.length > 1 && (
        <ul className="match-list">
          {matches.map((m) => (
            <li key={m.customer_id}>
              <button
                type="button"
                className={`match-item${selectedId === m.customer_id ? ' match-item--active' : ''}`}
                onClick={() => void selectCustomer(m.customer_id)}
              >
                <span className="match-item__name">{fullName(m)}</span>
                <span className="match-item__meta">
                  {[m.segment, [m.city, m.state].filter(Boolean).join(', ')]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {profileLoading && <div className="status-msg">Loading profile…</div>}
      {profileError && <div className="status-msg status-msg--error">{profileError}</div>}
      {profile && <ProfileCard profile={profile} />}
    </section>
  )
}
