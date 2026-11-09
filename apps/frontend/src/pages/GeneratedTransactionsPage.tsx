import { Eye } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { listAccounts } from '../api/accounts'
import { listCards } from '../api/cards'
import { listCustomers } from '../api/customers'
import { maskCardNumber } from '../lib/format'
import type { Transaction } from '../types/transaction'

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}

export default function GeneratedTransactionsPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const transactions = (location.state as { transactions?: Transaction[] } | null)?.transactions
  const [accountNumbers, setAccountNumbers] = useState<Record<string, string>>({})
  const [customerNames, setCustomerNames] = useState<Record<string, string>>({})
  const [cardNumbers, setCardNumbers] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!transactions) return
    async function load() {
      try {
        const [accts, custs, cards] = await Promise.all([listAccounts(), listCustomers(), listCards()])
        setCardNumbers(Object.fromEntries(cards.map((c) => [c.card_id, maskCardNumber(c.card_number)])))
        setAccountNumbers(Object.fromEntries(accts.map((a) => [a.account_id, a.account_number])))
        setCustomerNames(
          Object.fromEntries(custs.map((c) => [c.customer_id, `${c.first_name} ${c.last_name}`])),
        )
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'Failed to load account and customer names')
      }
    }
    void load()
  }, [transactions])

  if (!transactions) {
    return (
      <div>
        <div className="page-header">
          <h1>Generated transactions</h1>
          <Link to="/transactions" className="btn btn--secondary">Back to transactions</Link>
        </div>
        <div className="status-msg">No generated transactions to display.</div>
      </div>
    )
  }

  const sorted = [...transactions].sort((a, b) =>
    String(b.transacted_at ?? '').localeCompare(String(a.transacted_at ?? '')),
  )

  return (
    <div>
      <div className="page-header">
        <h1>Generated transactions ({transactions.length})</h1>
        <Link to="/transactions" className="btn btn--secondary">Back to transactions</Link>
      </div>

      {error && <div className="status-msg status-msg--error">{error}</div>}

      <table className="table">
        <thead>
          <tr>
            <th>Transacted</th><th>Type</th><th>Amount</th><th>Account #</th><th>Card</th><th>Customer</th><th>Merchant</th><th>Category</th><th>Status</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((t) => (
            <tr key={t.transaction_id}>
              <td>{formatDateTime(t.transacted_at)}</td>
              <td>{t.transaction_type}</td>
              <td>{t.amount} {t.currency ?? ''}</td>
              <td>{t.account_id ? (accountNumbers[t.account_id] ?? t.account_id) : '—'}</td>
              <td>{t.card_id ? (cardNumbers[t.card_id] ?? t.card_id) : '—'}</td>
              <td>{customerNames[t.customer_id] ?? t.customer_id}</td>
              <td>{t.merchant_name ?? '—'}</td>
              <td>{t.merchant_category ?? '—'}</td>
              <td>{t.status ?? '—'}</td>
              <td>
                <div className="row-actions">
                  <button className="icon-btn" aria-label="View" onClick={() => navigate(`/transactions/${t.transaction_id}`)}><Eye size={18} /></button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
