import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { createTransaction } from '../api/transactions'
import { listAccounts } from '../api/accounts'
import { listCards } from '../api/cards'
import { maskCardNumber } from '../lib/format'
import type { Account } from '../types/account'
import type { Card } from '../types/card'
import type { TransactionCreate } from '../types/transaction'

const TYPES = ['CREDIT', 'DEBIT', 'TRANSFER', 'FEE', 'INTEREST']
const CHANNELS = ['ONLINE', 'ATM', 'POS', 'MOBILE', 'BRANCH']
const STATUSES = ['COMPLETED', 'PENDING', 'FAILED']
const CURRENCIES = [
  'USD',
  'EUR',
  'GBP',
  'JPY',
  'CAD',
  'AUD',
  'CHF',
  'CNY',
  'HKD',
  'NZD',
  'SGD',
  'SEK',
]

export default function TransactionFormPage() {
  const navigate = useNavigate()
  const [accounts, setAccounts] = useState<Account[]>([])
  const [cards, setCards] = useState<Card[]>([])
  const [accountId, setAccountId] = useState('')
  const [cardId, setCardId] = useState('')
  const [transactionType, setTransactionType] = useState('CREDIT')
  const [amount, setAmount] = useState('')
  const [currency, setCurrency] = useState('USD')
  const [channel, setChannel] = useState('ONLINE')
  const [description, setDescription] = useState('')
  const [merchantName, setMerchantName] = useState('')
  const [merchantCategory, setMerchantCategory] = useState('')
  const [merchantCity, setMerchantCity] = useState('')
  const [merchantState, setMerchantState] = useState('')
  const [status, setStatus] = useState('COMPLETED')
  const [errors, setErrors] = useState<{ accountId?: string; amount?: string }>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listAccounts()
      .then(setAccounts)
      .catch((e) => setSubmitError(e instanceof ApiError ? e.message : 'Failed to load accounts'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!accountId) return
    listCards(accountId)
      .then((crds) => {
        setCards(crds)
        setCardId((prev) => (crds.some((c) => c.card_id === prev) ? prev : ''))
      })
      .catch((e) => setSubmitError(e instanceof ApiError ? e.message : 'Failed to load cards'))
  }, [accountId])

  function handleAccountChange(id: string) {
    setAccountId(id)
    setCardId('')
    if (!id) {
      setCards([])
      return
    }
    const acct = accounts.find((a) => a.account_id === id)
    if (acct?.currency) {
      setCurrency(acct.currency)
    }
  }

  function validate(): boolean {
    const next: typeof errors = {}
    if (!accountId) next.accountId = 'An account is required'
    if (amount.trim() === '' || Number.isNaN(Number(amount))) next.amount = 'A valid amount is required'
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitError(null)
    if (!validate()) return
    const account = accounts.find((a) => a.account_id === accountId)
    if (!account) {
      setErrors({ accountId: 'An account is required' })
      return
    }
    const payload: TransactionCreate = {
      account_id: accountId,
      customer_id: account.customer_id,
      transaction_type: transactionType,
      amount: Number(amount),
      currency: currency.trim() || 'USD',
      channel,
      status,
    }
    if (cardId) payload.card_id = cardId
    if (description.trim()) payload.description = description.trim()
    if (merchantName.trim()) payload.merchant_name = merchantName.trim()
    if (merchantCategory.trim()) payload.merchant_category = merchantCategory.trim()
    if (merchantCity.trim()) payload.merchant_city = merchantCity.trim()
    if (merchantState.trim()) payload.merchant_state = merchantState.trim()
    try {
      await createTransaction(payload)
      navigate('/transactions')
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : 'Failed to save transaction')
    }
  }

  if (loading) return <div className="status-msg">Loading…</div>

  return (
    <div>
      <div className="page-header">
        <h1>New transaction</h1>
      </div>
      <form className="form" onSubmit={onSubmit} noValidate>
        <div className="form__row">
          <label htmlFor="account_id">Account</label>
          <select id="account_id" value={accountId} onChange={(e) => handleAccountChange(e.target.value)}>
            <option value="">Select an account…</option>
            {accounts.map((a) => (
              <option key={a.account_id} value={a.account_id}>
                {a.account_number} ({a.account_type})
              </option>
            ))}
          </select>
          {errors.accountId && <span className="field-error">{errors.accountId}</span>}
        </div>

        <div className="form__row">
          <label htmlFor="card_id">Card</label>
          <select
            id="card_id"
            value={cardId}
            onChange={(e) => setCardId(e.target.value)}
            disabled={!accountId}
          >
            <option value="">No card</option>
            {cards.map((c) => (
              <option key={c.card_id} value={c.card_id}>
                {maskCardNumber(c.card_number)} ({c.card_brand} {c.card_type})
              </option>
            ))}
          </select>
        </div>

        <div className="form__row">
          <label htmlFor="transaction_type">Type</label>
          <select id="transaction_type" value={transactionType} onChange={(e) => setTransactionType(e.target.value)}>
            {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>

        <div className="form__row">
          <label htmlFor="amount">Amount</label>
          <input id="amount" type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />
          {errors.amount && <span className="field-error">{errors.amount}</span>}
        </div>

        <div className="form__row">
          <label htmlFor="currency">Currency</label>
          <select id="currency" value={currency} onChange={(e) => setCurrency(e.target.value)}>
            {CURRENCIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>

        <div className="form__row">
          <label htmlFor="channel">Channel</label>
          <select id="channel" value={channel} onChange={(e) => setChannel(e.target.value)}>
            {CHANNELS.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        <div className="form__row">
          <label htmlFor="description">Description</label>
          <input id="description" value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>

        <div className="form__row">
          <label htmlFor="merchant_name">Merchant</label>
          <input id="merchant_name" value={merchantName} onChange={(e) => setMerchantName(e.target.value)} />
        </div>

        <div className="form__row">
          <label htmlFor="merchant_category">Merchant category</label>
          <input id="merchant_category" value={merchantCategory} onChange={(e) => setMerchantCategory(e.target.value)} />
        </div>

        <div className="form__row">
          <label htmlFor="merchant_city">Merchant city</label>
          <input id="merchant_city" value={merchantCity} onChange={(e) => setMerchantCity(e.target.value)} />
        </div>

        <div className="form__row">
          <label htmlFor="merchant_state">Merchant state</label>
          <input id="merchant_state" value={merchantState} onChange={(e) => setMerchantState(e.target.value)} />
        </div>

        <div className="form__row">
          <label htmlFor="status">Status</label>
          <select id="status" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        {submitError && <div className="form__error">{submitError}</div>}
        <div className="form__actions">
          <button type="submit" className="btn">Save</button>
          <button type="button" className="btn btn--secondary" onClick={() => navigate('/transactions')}>Cancel</button>
        </div>
      </form>
    </div>
  )
}
