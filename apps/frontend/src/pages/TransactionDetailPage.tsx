import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { getTransaction } from '../api/transactions'
import type { Transaction } from '../types/transaction'

const FIELDS: [keyof Transaction, string][] = [
  ['transaction_type', 'Type'],
  ['amount', 'Amount'],
  ['currency', 'Currency'],
  ['account_id', 'Account ID'],
  ['customer_id', 'Customer ID'],
  ['description', 'Description'],
  ['merchant_name', 'Merchant'],
  ['merchant_category', 'Merchant category'],
  ['merchant_city', 'Merchant city'],
  ['merchant_state', 'Merchant state'],
  ['zip', 'Zip'],
  ['card_id', 'Card ID'],
  ['use_chip', 'Use chip'],
  ['channel', 'Channel'],
  ['status', 'Status'],
  ['transacted_at', 'Transacted at'],
  ['posted_at', 'Posted at'],
]

export default function TransactionDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [transaction, setTransaction] = useState<Transaction | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    setError(null)
    getTransaction(id)
      .then(setTransaction)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Failed to load transaction'))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return <div className="status-msg">Loading…</div>
  if (error) return <div className="status-msg status-msg--error">{error}</div>
  if (!transaction) return null

  return (
    <div className="detail">
      <div className="page-header">
        <h1>Transaction {transaction.transaction_id}</h1>
        <Link to="/transactions" className="btn btn--secondary">Back</Link>
      </div>
      <dl>
        {FIELDS.map(([key, label]) => (
          <div key={key} style={{ display: 'contents' }}>
            <dt>{label}</dt>
            <dd>{(transaction[key] as string | number | null) ?? '—'}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
