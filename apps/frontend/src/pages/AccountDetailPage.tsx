import { CreditCard } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { getAccount } from '../api/accounts'
import { createCard, listCards, updateCard } from '../api/cards'
import type { Account } from '../types/account'
import { maskCardNumber } from '../lib/format'
import type { Card, CardCreate, CardUpdate } from '../types/card'

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

const CARD_BRANDS = ['VISA', 'MASTERCARD', 'AMEX', 'DISCOVER', 'OTHER']
const CARD_TYPES = ['DEBIT', 'CREDIT']

interface NewCardForm {
  card_brand: string
  card_type: string
  card_number: string
  expires: string
  has_chip: boolean
  credit_limit: string
}

// Default expiry: four years out, as an ISO date (the API expects a full date).
function emptyNewCard(): NewCardForm {
  const now = new Date()
  return {
    card_brand: 'VISA',
    card_type: 'DEBIT',
    card_number: '',
    expires: new Date(now.getFullYear() + 4, now.getMonth(), 1).toISOString().slice(0, 10),
    has_chip: true,
    credit_limit: '',
  }
}

export default function AccountDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [account, setAccount] = useState<Account | null>(null)
  const [cards, setCards] = useState<Card[]>([])
  const [cardsError, setCardsError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingCardId, setEditingCardId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<CardUpdate>({})
  const [editError, setEditError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [showNewCard, setShowNewCard] = useState(false)
  const [newCard, setNewCard] = useState<NewCardForm>(emptyNewCard)
  const [newCardError, setNewCardError] = useState<string | null>(null)
  const [creatingCard, setCreatingCard] = useState(false)

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

  async function saveCard(cardId: string) {
    setEditError(null)
    if (Object.keys(editForm).length === 0) {
      setEditingCardId(null)
      return
    }
    try {
      await updateCard(cardId, editForm)
      const refreshed = await listCards(id!)
      setCards(refreshed)
      setEditingCardId(null)
      setEditForm({})
      setSuccessMsg('Card updated successfully.')
      setTimeout(() => setSuccessMsg(null), 3000)
    } catch (e) {
      setEditError(e instanceof ApiError ? e.message : 'Failed to update card')
    }
  }

  function openNewCard() {
    setNewCard(emptyNewCard())
    setNewCardError(null)
    setShowNewCard(true)
  }

  function closeNewCard() {
    setShowNewCard(false)
    setNewCardError(null)
  }

  function setNewCardField<K extends keyof NewCardForm>(key: K, value: NewCardForm[K]) {
    setNewCard((prev) => ({ ...prev, [key]: value }))
  }

  async function submitNewCard(e: React.FormEvent) {
    e.preventDefault()
    setNewCardError(null)
    const number = newCard.card_number.replace(/\s+/g, '')
    if (!/^\d{12,19}$/.test(number)) {
      setNewCardError('Card number must be 12 to 19 digits.')
      return
    }
    const data: CardCreate = {
      account_id: id!,
      card_brand: newCard.card_brand,
      card_type: newCard.card_type,
      card_number: number,
      expires: newCard.expires,
      has_chip: newCard.has_chip,
      credit_limit:
        newCard.card_type === 'CREDIT' && newCard.credit_limit !== '' ? newCard.credit_limit : null,
    }
    setCreatingCard(true)
    try {
      await createCard(data)
      setCards(await listCards(id!))
      setShowNewCard(false)
      setSuccessMsg('Card created successfully.')
      setTimeout(() => setSuccessMsg(null), 3000)
    } catch (err) {
      setNewCardError(err instanceof ApiError ? err.message : 'Failed to create card')
    } finally {
      setCreatingCard(false)
    }
  }

  function cancelEdit() {
    setEditingCardId(null)
    setEditForm({})
    setEditError(null)
  }

  function setEditField<K extends keyof CardUpdate>(key: K, value: string) {
    setEditForm((prev) => ({ ...prev, [key]: value }))
  }

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
        <button
          type="button"
          className="icon-btn"
          title="Add card"
          aria-label="Add card"
          onClick={showNewCard ? closeNewCard : openNewCard}
        >
          <CreditCard size={20} />
          <span aria-hidden="true" style={{ fontWeight: 700, marginLeft: 2 }}>+</span>
        </button>
      </div>

      {showNewCard && (
        <form
          className="form"
          aria-label="New card"
          onSubmit={submitNewCard}
          style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10, padding: 12, background: '#f8f9fa', borderRadius: 6, marginBottom: 12 }}
        >
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
            Brand
            <select value={newCard.card_brand} onChange={(e) => setNewCardField('card_brand', e.target.value)}>
              {CARD_BRANDS.map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
            Type
            <select value={newCard.card_type} onChange={(e) => setNewCardField('card_type', e.target.value)}>
              {CARD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
            Card number
            <input
              type="text"
              inputMode="numeric"
              required
              value={newCard.card_number}
              onChange={(e) => setNewCardField('card_number', e.target.value)}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
            Expires
            <input type="date" required value={newCard.expires} onChange={(e) => setNewCardField('expires', e.target.value)} />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
            Chip
            <select value={newCard.has_chip ? 'true' : 'false'} onChange={(e) => setNewCardField('has_chip', e.target.value === 'true')}>
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          </label>
          {newCard.card_type === 'CREDIT' && (
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
              Credit limit
              <input type="number" step="0.01" min="0" value={newCard.credit_limit} onChange={(e) => setNewCardField('credit_limit', e.target.value)} />
            </label>
          )}
          <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 8, alignItems: 'center' }}>
            <button type="submit" className="btn" style={{ fontSize: 12 }} disabled={creatingCard}>
              {creatingCard ? 'Creating…' : 'Create card'}
            </button>
            <button type="button" className="btn btn--secondary" style={{ fontSize: 12 }} onClick={closeNewCard}>Cancel</button>
            {newCardError && <span className="field-error" style={{ fontSize: 12 }}>{newCardError}</span>}
          </div>
        </form>
      )}

      {cardsError && <div className="status-msg status-msg--error">{cardsError}</div>}

      <table className="table">
        <thead>
          <tr>
            <th>Card #</th><th>Brand</th><th>Type</th><th>Expires</th><th>Chip</th><th>Credit limit</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {cards.map((c) => {
            const isEditing = editingCardId === c.card_id
            return (
              <tr key={c.card_id}>
                <td>{isEditing ? c.card_number : maskCardNumber(c.card_number)}</td>
                {isEditing ? (
                  <td colSpan={6}>
                    <div className="form" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 10, padding: 8, background: '#f8f9fa', borderRadius: 6 }}>
                      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                        Brand
                        <select value={editForm.card_brand ?? c.card_brand} onChange={(e) => setEditField('card_brand', e.target.value)}>
                          {CARD_BRANDS.map((b) => <option key={b} value={b}>{b}</option>)}
                        </select>
                      </label>
                      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                        Type
                        <select value={editForm.card_type ?? c.card_type} onChange={(e) => setEditField('card_type', e.target.value)}>
                          {CARD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                        </select>
                      </label>
                      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                        Expires
                        <input type="month" value={editForm.expires ?? c.expires} onChange={(e) => setEditField('expires', e.target.value)} />
                      </label>
                      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                        Chip
                        <select value={editForm.has_chip != null ? (editForm.has_chip ? 'true' : 'false') : (c.has_chip ? 'true' : 'false')} onChange={(e) => setEditField('has_chip', e.target.value === 'true')}> <option value="true">Yes</option><option value="false">No</option></select>
                      </label>
                      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                        Credit limit
                        <input type="number" step="0.01" value={editForm.credit_limit ?? (c.credit_limit != null ? String(c.credit_limit) : '')} onChange={(e) => setEditField('credit_limit', e.target.value)} />
                      </label>
                    </div>
                    <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                      <button className="btn" style={{ fontSize: 12 }} onClick={() => saveCard(c.card_id)}>Save</button>
                      <button className="btn btn--secondary" style={{ fontSize: 12 }} onClick={cancelEdit}>Cancel</button>
                    </div>
                    {editError && <span className="field-error" style={{ fontSize: 12 }}>{editError}</span>}
                  </td>
                ) : (
                  <>
                    <td>{c.card_brand}</td>
                    <td>{c.card_type}</td>
                    <td>{c.expires}</td>
                    <td>{c.has_chip ? 'Yes' : 'No'}</td>
                    <td>{c.credit_limit ?? '—'}</td>
                    <td><button className="btn btn--small" onClick={() => {
                      setEditingCardId(c.card_id)
                      setEditForm({
                        card_brand: c.card_brand,
                        card_type: c.card_type,
                        expires: c.expires,
                        has_chip: c.has_chip,
                        credit_limit: c.credit_limit != null ? String(c.credit_limit) : '',
                      })
                      setEditError(null)
                    }}>Edit</button></td>
                  </>
                )}
              </tr>
            )
          })}
          {cards.length === 0 && !cardsError && (
            <tr><td colSpan={7} className="status-msg">No cards yet.</td></tr>
          )}
        </tbody>
      </table>
      {successMsg && <span className="status-msg" style={{ display: 'block', marginTop: 8 }}>{successMsg}</span>}
    </div>
  )
}
