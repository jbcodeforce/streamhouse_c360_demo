import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { createCustomer, getCustomer, updateCustomer } from '../api/customers'
import type { CustomerCreate } from '../types/customer'

type FormState = Record<keyof CustomerCreate, string>

const EMPTY: FormState = {
  first_name: '', last_name: '', email: '', phone: '', date_of_birth: '', gender: '',
  address: '', city: '', state: '', postal_code: '',
  country: 'US', customer_since: '', segment: '', status: 'ACTIVE',
}

const TEXT_FIELDS: [keyof CustomerCreate, string, string?][] = [
  ['first_name', 'First name'],
  ['last_name', 'Last name'],
  ['email', 'Email', 'email'],
  ['phone', 'Phone'],
  ['date_of_birth', 'Date of birth', 'date'],
  ['gender', 'Gender'],
  ['address', 'Address'],
  ['city', 'City'],
  ['state', 'State'],
  ['postal_code', 'Postal code'],
  ['country', 'Country'],
  ['customer_since', 'Customer since', 'date'],
  ['segment', 'Segment'],
  ['status', 'Status'],
]

// Fields rendered as <input type="date">, which only accepts yyyy-MM-dd.
// The backend may serialize these as full datetimes (e.g. date_of_birth),
// so loaded values are trimmed to the date portion.
const DATE_FIELDS = new Set<keyof CustomerCreate>(
  TEXT_FIELDS.filter(([, , type]) => type === 'date').map(([key]) => key),
)

function toPayload(form: FormState): CustomerCreate {
  const out = {} as Record<string, string>
  for (const key of Object.keys(form) as (keyof FormState)[]) {
    const value = form[key].trim()
    // Omit empty fields rather than sending null: the backend's non-optional
    // defaulted fields (country, customer_since, status) reject an explicit
    // null (422) and apply their default only when the key is absent.
    if (value !== '') {
      out[key] = value
    }
  }
  // Required fields are guaranteed present by validation before this runs.
  return out as unknown as CustomerCreate
}

export default function CustomerFormPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const isEdit = Boolean(id)

  const [form, setForm] = useState<FormState>(EMPTY)
  const [errors, setErrors] = useState<Partial<Record<keyof CustomerCreate, string>>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [loading, setLoading] = useState(isEdit)

  useEffect(() => {
    if (!id) return
    getCustomer(id)
      .then((c) => {
        const next = { ...EMPTY }
        for (const key of Object.keys(EMPTY) as (keyof FormState)[]) {
          const v = c[key]
          if (v == null) {
            next[key] = ''
          } else {
            const s = String(v)
            next[key] = DATE_FIELDS.has(key) ? s.slice(0, 10) : s
          }
        }
        setForm(next)
      })
      .catch((e) => setSubmitError(e instanceof ApiError ? e.message : 'Failed to load customer'))
      .finally(() => setLoading(false))
  }, [id])

  function validate(): boolean {
    const next: Partial<Record<keyof CustomerCreate, string>> = {}
    if (!form.first_name.trim()) next.first_name = 'First name is required'
    if (!form.last_name.trim()) next.last_name = 'Last name is required'
    if (!form.email.trim()) next.email = 'Email is required'
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitError(null)
    if (!validate()) return
    const payload = toPayload(form)
    try {
      if (isEdit && id) {
        await updateCustomer(id, payload)
      } else {
        await createCustomer(payload)
      }
      navigate('/customers')
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : 'Failed to save customer')
    }
  }

  if (loading) return <div className="status-msg">Loading…</div>

  return (
    <div>
      <div className="page-header">
        <h1>{isEdit ? 'Edit customer' : 'New customer'}</h1>
      </div>
      <form className="form" onSubmit={onSubmit} noValidate>
        {TEXT_FIELDS.map(([key, label, type]) => (
          <div className="form__row" key={key}>
            <label htmlFor={key}>{label}</label>
            <input
              id={key}
              type={type ?? 'text'}
              value={form[key]}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
            />
            {errors[key] && <span className="field-error">{errors[key]}</span>}
          </div>
        ))}
        {submitError && <div className="form__error">{submitError}</div>}
        <div className="form__actions">
          <button type="submit" className="btn">Save</button>
          <button type="button" className="btn btn--secondary" onClick={() => navigate('/customers')}>Cancel</button>
        </div>
      </form>
    </div>
  )
}
