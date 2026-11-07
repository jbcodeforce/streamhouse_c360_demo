import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { getAccount } from '../api/accounts'
import { listCards } from '../api/cards'
import type { Account } from '../types/account'
import type { Card } from '../types/card'

function maskCardNumber(n: string): string {
  return `•••• ${n.slice(-4)}`
}

const FIELDS: [keyof Account, string][] = [
  ['account_number', 'Account number'],
  ['account_type', 'Account type'],
  ['customer_id', 'Customer ID'],
  ['currency', 'Currency'],
  ['balance', 'Balance'],
  ['credit_limit', 'Credit limit'],
  ['opened_date', 'Opened date'],
  ['closed_date', 'Closed date'],
  ['status', 'Status'],
]

export default function AccountDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [account, setAccount] = useState<Account | null>(null)
  const [cards, setCards] = useState<Card[]>([])
  const [cardsError, setCardsError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    setError(null)
    getAccount(id)
      .then(setAccount)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Failed to load account'))
      .finally(() => setLoading(false))
    setCardsError(null)
    listCards(id)
      .then(setCards)
      .catch((e) => setCardsError(e instanceof ApiError ? e.message : 'Failed to load cards'))
  }, [id])

  if (loading) return <div className="status-msg">Loading…</div>
  if (error) return <div className="status-msg status-msg--error">{error}</div>
  if (!account) return null

  return (
    <div className="detail">
      <div className="page-header">
        <h1>Account {account.account_number}</h1>
        <div style={{ display: 'flex', gap: 10 }}>
          <Link to={`/accounts/${account.account_id}/edit`} className="btn">Edit</Link>
          <Link to={`/customers/${account.customer_id}`} className="btn btn--secondary">Back</Link>
        </div>
      </div>
      <dl>
        {FIELDS.map(([key, label]) => (
          <div key={key} style={{ display: 'contents' }}>
            <dt>{label}</dt>
            <dd>{(account[key] as string | number | null) ?? '—'}</dd>
          </div>
        ))}
      </dl>

      <div className="page-header" style={{ marginTop: 32 }}>
        <h2 style={{ margin: 0 }}>Cards</h2>
      </div>

      {cardsError && <div className="status-msg status-msg--error">{cardsError}</div>}

      <table className="table">
        <thead>
          <tr>
            <th>Card #</th><th>Brand</th><th>Type</th><th>Expires</th><th>Chip</th><th>Credit limit</th>
          </tr>
        </thead>
        <tbody>
          {cards.map((c) => (
            <tr key={c.card_id}>
              <td>{maskCardNumber(c.card_number)}</td>
              <td>{c.card_brand}</td>
              <td>{c.card_type}</td>
              <td>{c.expires}</td>
              <td>{c.has_chip ? 'Yes' : 'No'}</td>
              <td>{c.credit_limit ?? '—'}</td>
            </tr>
          ))}
          {cards.length === 0 && !cardsError && (
            <tr><td colSpan={6} className="status-msg">No cards yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
