import { Eye } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { generateTransactions, listTransactions } from '../api/transactions'
import { listAccounts } from '../api/accounts'
import { listCards } from '../api/cards'
import { listCustomers } from '../api/customers'
import { maskCardNumber } from '../lib/format'
import type { Transaction } from '../types/transaction'

export default function TransactionsPage() {
  const navigate = useNavigate()
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [accountNumbers, setAccountNumbers] = useState<Record<string, string>>({})
  const [customerNames, setCustomerNames] = useState<Record<string, string>>({})
  const [cardNumbers, setCardNumbers] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const [generateError, setGenerateError] = useState<string | null>(null)

  async function handleGenerate() {
    setGenerating(true)
    setGenerateError(null)
    try {
      const generated = await generateTransactions()
      navigate('/transactions/generated', { state: { transactions: generated } })
    } catch (e) {
      setGenerateError(e instanceof ApiError ? e.message : 'Failed to generate transactions')
      setGenerating(false)
    }
  }

  useEffect(() => {
    async function load() {
      try {
        const [txns, accts, custs, cards] = await Promise.all([
          listTransactions(), listAccounts(), listCustomers(), listCards(),
        ])
        setTransactions(txns)
        setCardNumbers(Object.fromEntries(cards.map((c) => [c.card_id, maskCardNumber(c.card_number)])))
        setAccountNumbers(Object.fromEntries(accts.map((a) => [a.account_id, a.account_number])))
        setCustomerNames(
          Object.fromEntries(custs.map((c) => [c.customer_id, `${c.first_name} ${c.last_name}`])),
        )
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'Failed to load transactions')
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [])

  return (
    <div>
      <div className="page-header">
        <h1>Transactions</h1>
        <div className="row-actions">
          <button className="btn btn--secondary" onClick={() => void handleGenerate()} disabled={generating}>
            {generating ? 'Generating…' : 'Generate 200 transactions'}
          </button>
          <Link to="/transactions/new" className="btn">Add transaction</Link>
        </div>
      </div>

      {generateError && <div className="status-msg status-msg--error">{generateError}</div>}
      {loading && <div className="status-msg">Loading…</div>}
      {error && <div className="status-msg status-msg--error">{error}</div>}

      {!loading && !error && (
        <table className="table">
          <thead>
            <tr>
              <th>Transacted</th><th>Type</th><th>Amount</th><th>Account #</th><th>Card</th><th>Customer</th><th>Merchant</th><th>Category</th><th>Status</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((t) => (
              <tr key={t.transaction_id}>
                <td>{t.transacted_at ? String(t.transacted_at).slice(0, 10) : '—'}</td>
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
            {transactions.length === 0 && (
              <tr><td colSpan={10} className="status-msg">No transactions yet.</td></tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  )
}
