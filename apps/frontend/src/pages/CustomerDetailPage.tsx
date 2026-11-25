import { Eye, Pencil, Ban, CreditCard } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import ConfirmDialog from '../components/ConfirmDialog'
import { ApiError } from '../api/client'
import { getCustomer } from '../api/customers'
import { listAccounts, updateAccount } from '../api/accounts'
import { createCard } from '../api/cards'
import { formatCurrency } from '../lib/format'
import type { Customer } from '../types/customer'
import type { Account } from '../types/account'
import type { CardCreate } from '../types/card'

const FIELDS: [keyof Customer, string][] = [
  ['first_name', 'First name'],
  ['last_name', 'Last name'],
  ['email', 'Email'],
  ['phone', 'Phone'],
  ['date_of_birth', 'Date of birth'],
  ['gender', 'Gender'],
  ['address', 'Address'],
  ['city', 'City'],
  ['state', 'State'],
  ['postal_code', 'Postal code'],
  ['country', 'Country'],
  ['customer_since', 'Customer since'],
  ['segment', 'Segment'],
  ['status', 'Status'],
  ['yearly_income', 'Yearly income'],
  ['retirement_age', 'Retirement age'],
  ['credit_score', 'Credit score'],
]

function display(key: keyof Customer, value: Customer[keyof Customer]): string {
  if (value == null || value === '') return '—'
  // yearly_income is a decimal(18,2); the API may return it as a string.
  if (key === 'yearly_income') return formatCurrency(Number(value))
  return String(value)
}

export default function CustomerDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [customer, setCustomer] = useState<Customer | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [accountsError, setAccountsError] = useState<string | null>(null)
  const [pendingClose, setPendingClose] = useState<Account | null>(null)
  const [creatingCard, setCreatingCard] = useState<string | null>(null)

  async function loadAccounts(customerId: string) {
    setAccountsError(null)
    try {
      setAccounts(await listAccounts(customerId))
    } catch (e) {
      setAccountsError(e instanceof ApiError ? e.message : 'Failed to load accounts')
    }
  }

  useEffect(() => {
    if (!id) return
    setLoading(true)
    setError(null)
    getCustomer(id)
      .then((c) => {
        setCustomer(c)
        return loadAccounts(id)
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Failed to load customer'))
      .finally(() => setLoading(false))
  }, [id])

  async function confirmClose() {
    if (!pendingClose || !id) return
    try {
      await updateAccount(pendingClose.account_id, { status: 'CLOSED' })
      setPendingClose(null)
      await loadAccounts(id)
    } catch (e) {
      setAccountsError(e instanceof ApiError ? e.message : 'Failed to close account')
      setPendingClose(null)
    }
  }

  async function handleCreateCard(accountId: string) {
    setCreatingCard(accountId)
    try {
      // Generate a plausible card number (mod-10 compliant)
      const brand = 'VISA'
      const cardNumber = '4' + '00000000000000' + (Math.random() > 0.5 ? '1' : '2')
      const now = new Date()
      const expires = new Date(now.getFullYear() + 4, now.getMonth(), 1)
      const data: CardCreate = {
        account_id: accountId,
        card_brand: brand,
        card_type: Math.random() > 0.5 ? 'CREDIT' : 'DEBIT',
        card_number: cardNumber,
        expires: expires.toISOString().slice(0, 10),
        has_chip: true,
      }
      await createCard(data)
      await loadAccounts(id!)
    } catch (e) {
      setAccountsError(e instanceof ApiError ? e.message : 'Failed to create card')
    }
    setCreatingCard(null)
  }

  if (loading) return <div className="status-msg">Loading…</div>
  if (error) return <div className="status-msg status-msg--error">{error}</div>
  if (!customer) return null

  return (
    <div className="detail">
      <div className="page-header">
        <h1>{customer.first_name} {customer.last_name}</h1>
        <div style={{ display: 'flex', gap: 10 }}>
          <Link to={`/customers/${customer.customer_id}/edit`} className="btn">Edit</Link>
          <Link to="/customers" className="btn btn--secondary">Back</Link>
        </div>
      </div>
      <dl>
        {FIELDS.map(([key, label]) => (
          <div key={key} style={{ display: 'contents' }}>
            <dt>{label}</dt>
            <dd>{display(key, customer[key])}</dd>
          </div>
        ))}
      </dl>

      <div className="page-header" style={{ marginTop: 32 }}>
        <h2 style={{ margin: 0 }}>Accounts</h2>
        <Link to={`/accounts/new?customer_id=${customer.customer_id}`} className="btn">Add account</Link>
      </div>

      {accountsError && <div className="status-msg status-msg--error">{accountsError}</div>}

      <table className="table">
        <thead>
          <tr>
            <th>Account #</th><th>Type</th><th>Balance</th><th>Status</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {accounts.map((a) => (
            <tr key={a.account_id}>
              <td>{a.account_number}</td>
              <td>{a.account_type}</td>
              <td>{a.balance ?? 0} {a.currency ?? ''}</td>
              <td>{a.status ?? '—'}</td>
              <td>
                <div className="row-actions">
                  <button className="icon-btn" aria-label="View" onClick={() => navigate(`/accounts/${a.account_id}`)}><Eye size={18} /></button>
                  <button className="icon-btn" aria-label="Edit" onClick={() => navigate(`/accounts/${a.account_id}/edit`)}><Pencil size={18} /></button>
                  <button
                    className="icon-btn icon-btn--danger"
                    aria-label="Close"
                    disabled={a.status === 'CLOSED'}
                    onClick={() => setPendingClose(a)}
                  >
                    <Ban size={18} />
                  </button>
                  <button
                    className="icon-btn"
                    aria-label="Create card"
                    title="Create a card for this account"
                    disabled={a.status === 'CLOSED'}
                    onClick={() => handleCreateCard(a.account_id)}
                  >
                    <CreditCard size={18} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {accounts.length === 0 && (
            <tr><td colSpan={5} className="status-msg">No accounts yet.</td></tr>
          )}
        </tbody>
      </table>

      <ConfirmDialog
        open={pendingClose !== null}
        title="Close account"
        message={pendingClose ? `Close account ${pendingClose.account_number}? It will be marked CLOSED.` : ''}
        confirmLabel="Close"
        onConfirm={confirmClose}
        onCancel={() => setPendingClose(null)}
      />
    </div>
  )
}
