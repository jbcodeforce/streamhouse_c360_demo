import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { createAccount, getAccount, updateAccount } from '../api/accounts'
import { listCustomers } from '../api/customers'
import type { AccountCreate } from '../types/account'
import type { Customer } from '../types/customer'

type FormState = Record<keyof AccountCreate, string>

const EMPTY: FormState = {
  customer_id: '', account_number: '', account_type: 'CHECKING', currency: 'USD',
  balance: '', credit_limit: '', opened_date: '', closed_date: '', status: 'ACTIVE',
}

const ACCOUNT_TYPES = ['CHECKING', 'SAVINGS', 'CREDIT', 'LOAN']
const STATUSES = ['ACTIVE', 'CLOSED', 'FROZEN']
const DATE_FIELDS = new Set<keyof AccountCreate>(['opened_date', 'closed_date'])

function toPayload(form: FormState): AccountCreate {
  const out = {} as Record<string, string | number>
  for (const key of Object.keys(form) as (keyof FormState)[]) {
    const value = form[key].trim()
    if (value === '') continue
    if (key === 'balance' || key === 'credit_limit') {
      out[key] = Number(value)
    } else {
      out[key] = value
    }
  }
  return out as unknown as AccountCreate
}

export default function AccountFormPage() {
  const { customerId, accountId } = useParams<{ customerId?: string; accountId?: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const isEdit = Boolean(accountId)
  const presetCustomerId = customerId ?? searchParams.get('customer_id') ?? ''

  const [form, setForm] = useState<FormState>(
    presetCustomerId ? { ...EMPTY, customer_id: presetCustomerId } : EMPTY,
  )
  const [customers, setCustomers] = useState<Customer[]>([])
  const [errors, setErrors] = useState<Partial<Record<keyof AccountCreate, string>>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function init() {
      try {
        const [custs, account] = await Promise.all([
          listCustomers(),
          accountId ? getAccount(accountId) : Promise.resolve(null),
        ])
        setCustomers(custs)
        if (account) {
          const next = { ...EMPTY }
          for (const key of Object.keys(EMPTY) as (keyof FormState)[]) {
            const v = account[key]
            if (v == null) {
              next[key] = ''
            } else {
              const s = String(v)
              next[key] = DATE_FIELDS.has(key) ? s.slice(0, 10) : s
            }
          }
          setForm(next)
        }
      } catch (e) {
        setSubmitError(e instanceof ApiError ? e.message : 'Failed to load form')
      } finally {
        setLoading(false)
      }
    }
    void init()
  }, [accountId])

  function validate(): boolean {
    const next: Partial<Record<keyof AccountCreate, string>> = {}
    if (!form.customer_id.trim()) next.customer_id = 'Customer is required'
    if (!form.account_number.trim()) next.account_number = 'Account number is required'
    if (!form.account_type.trim()) next.account_type = 'Account type is required'
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitError(null)
    if (!validate()) return
    const payload = toPayload(form)
    try {
      if (isEdit && accountId) {
        await updateAccount(accountId, payload)
      } else {
        await createAccount(payload)
      }
      navigate(returnTo)
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : 'Failed to save account')
    }
  }

  function set<K extends keyof FormState>(key: K, value: string) {
    setForm({ ...form, [key]: value })
  }

  const customerLocked = Boolean(presetCustomerId) || (isEdit && accountId)
  const returnTo = form.customer_id ? `/customers/${form.customer_id}` : '/customers'

  const pageTitle = isEdit ? 'Edit account' : 'New account'
  if (loading) return <div className="status-msg">Loading…</div>

  return (
    <div>
      <div className="page-header">
        <h1>{pageTitle}</h1>
      </div>
      <form className="form" onSubmit={onSubmit} noValidate>
        <div className="form__row">
          <label htmlFor="customer_id">Customer</label>
          <select id="customer_id" value={form.customer_id} disabled={customerLocked} onChange={(e) => set('customer_id', e.target.value)}>
            <option value="">Select a customer…</option>
            {customers.map((c) => (
              <option key={c.customer_id} value={c.customer_id}>
                {c.first_name} {c.last_name} — {c.email}
              </option>
            ))}
          </select>
          {errors.customer_id && <span className="field-error">{errors.customer_id}</span>}
        </div>

        <div className="form__row">
          <label htmlFor="account_number">Account number</label>
          <input id="account_number" value={form.account_number} onChange={(e) => set('account_number', e.target.value)} />
          {errors.account_number && <span className="field-error">{errors.account_number}</span>}
        </div>

        <div className="form__row">
          <label htmlFor="account_type">Account type</label>
          <select id="account_type" value={form.account_type} onChange={(e) => set('account_type', e.target.value)}>
            {ACCOUNT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          {errors.account_type && <span className="field-error">{errors.account_type}</span>}
        </div>

        <div className="form__row">
          <label htmlFor="currency">Currency</label>
          <input id="currency" value={form.currency} onChange={(e) => set('currency', e.target.value)} />
        </div>

        <div className="form__row">
          <label htmlFor="balance">Balance</label>
          <input id="balance" type="number" step="0.01" value={form.balance} onChange={(e) => set('balance', e.target.value)} />
        </div>

        <div className="form__row">
          <label htmlFor="credit_limit">Credit limit</label>
          <input id="credit_limit" type="number" step="0.01" value={form.credit_limit} onChange={(e) => set('credit_limit', e.target.value)} />
        </div>

        <div className="form__row">
          <label htmlFor="opened_date">Opened date</label>
          <input id="opened_date" type="date" value={form.opened_date} onChange={(e) => set('opened_date', e.target.value)} />
        </div>

        <div className="form__row">
          <label htmlFor="closed_date">Closed date</label>
          <input id="closed_date" type="date" value={form.closed_date} onChange={(e) => set('closed_date', e.target.value)} />
        </div>

        <div className="form__row">
          <label htmlFor="status">Status</label>
          <select id="status" value={form.status} onChange={(e) => set('status', e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        {submitError && <div className="form__error">{submitError}</div>}
        <div className="form__actions">
          <button type="submit" className="btn">Save</button>
          <button type="button" className="btn btn--secondary" onClick={() => navigate(returnTo)}>Cancel</button>
        </div>
      </form>
    </div>
  )
}
