import { Eye, Pencil, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import ConfirmDialog from '../components/ConfirmDialog'
import { ApiError } from '../api/client'
import { deleteCustomer, listCustomers } from '../api/customers'
import { formatCurrency } from '../lib/format'
import type { Customer } from '../types/customer'

export default function CustomersPage() {
  const navigate = useNavigate()
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<Customer | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setCustomers(await listCustomers())
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load customers')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  async function confirmDelete() {
    if (!pendingDelete) return
    try {
      await deleteCustomer(pendingDelete.customer_id)
      setPendingDelete(null)
      await load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to delete customer')
      setPendingDelete(null)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>Customers</h1>
        <Link to="/customers/new" className="btn">Add customer</Link>
      </div>

      {loading && <div className="status-msg">Loading…</div>}
      {error && <div className="status-msg status-msg--error">{error}</div>}

      {!loading && !error && (
        <table className="table">
          <thead>
            <tr>
              <th>Name</th><th>Email</th><th>Phone</th><th>Segment</th><th>Status</th>
              <th>Yearly income</th><th>Credit score</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {customers.map((c) => (
              <tr key={c.customer_id}>
                <td>{c.first_name} {c.last_name}</td>
                <td>{c.email}</td>
                <td>{c.phone ?? '—'}</td>
                <td>{c.segment ?? '—'}</td>
                <td>{c.status ?? '—'}</td>
                <td>{c.yearly_income != null ? formatCurrency(Number(c.yearly_income)) : '—'}</td>
                <td>{c.credit_score ?? '—'}</td>
                <td>
                  <div className="row-actions">
                    <button className="icon-btn" aria-label="View" onClick={() => navigate(`/customers/${c.customer_id}`)}><Eye size={18} /></button>
                    <button className="icon-btn" aria-label="Edit" onClick={() => navigate(`/customers/${c.customer_id}/edit`)}><Pencil size={18} /></button>
                    <button className="icon-btn icon-btn--danger" aria-label="Delete" onClick={() => setPendingDelete(c)}><Trash2 size={18} /></button>
                  </div>
                </td>
              </tr>
            ))}
            {customers.length === 0 && (
              <tr><td colSpan={8} className="status-msg">No customers yet.</td></tr>
            )}
          </tbody>
        </table>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete customer"
        message={pendingDelete ? `Delete ${pendingDelete.first_name} ${pendingDelete.last_name}? This cannot be undone.` : ''}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}
