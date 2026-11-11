import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as txnApi from '../api/transactions'
import * as acctApi from '../api/accounts'
import * as cardsApi from '../api/cards'
import TransactionFormPage from './TransactionFormPage'

const card = { card_id: 'k1', account_id: 'a1', card_brand: 'VISA', card_type: 'DEBIT', card_number: '4532010000079192', expires: '2027-01-28', has_chip: true, credit_limit: null, created_at: '', updated_at: '' }
const acct = { account_id: 'a1', customer_id: 'c1', account_number: 'CHK-1', account_type: 'CHECKING', currency: 'USD', balance: 0, credit_limit: null, opened_date: '2020-01-01', closed_date: null, status: 'ACTIVE', created_at: '', updated_at: '' }

beforeEach(() => {
  vi.spyOn(cardsApi, 'listCards').mockResolvedValue([card] as never)
})
afterEach(() => vi.restoreAllMocks())

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/transactions/new']}>
      <Routes>
        <Route path="/transactions/new" element={<TransactionFormPage />} />
        <Route path="/transactions" element={<div>list</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('TransactionFormPage', () => {
  it('validates required fields before submitting', async () => {
    vi.spyOn(acctApi, 'listAccounts').mockResolvedValue([acct] as never)
    const create = vi.spyOn(txnApi, 'createTransaction').mockResolvedValue({} as never)
    renderPage()
    await screen.findByRole('button', { name: /save/i })
    await userEvent.click(screen.getByRole('button', { name: /save/i }))
    expect(await screen.findByText(/an account is required/i)).toBeInTheDocument()
    expect(create).not.toHaveBeenCalled()
  })

  it('creates a transaction, deriving customer_id from the selected account', async () => {
    vi.spyOn(acctApi, 'listAccounts').mockResolvedValue([acct] as never)
    const create = vi.spyOn(txnApi, 'createTransaction').mockResolvedValue({} as never)
    renderPage()
    await screen.findByRole('button', { name: /save/i })
    await userEvent.selectOptions(screen.getByLabelText(/^account$/i), 'a1')
    await userEvent.type(screen.getByLabelText(/amount/i), '42.50')
    await userEvent.click(screen.getByRole('button', { name: /save/i }))
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    const payload = create.mock.calls[0][0]
    expect(payload).toMatchObject({ account_id: 'a1', customer_id: 'c1', amount: 42.5, transaction_type: 'CREDIT', currency: 'USD' })
  })

  it('loads cards for the selected account and allows card selection', async () => {
    vi.spyOn(acctApi, 'listAccounts').mockResolvedValue([acct] as never)
    const listCardsSpy = vi.spyOn(cardsApi, 'listCards').mockResolvedValue([card] as never)
    const create = vi.spyOn(txnApi, 'createTransaction').mockResolvedValue({} as never)
    renderPage()
    await screen.findByRole('button', { name: /save/i })
    expect(screen.getByLabelText(/^card$/i)).toBeDisabled()
    await userEvent.selectOptions(screen.getByLabelText(/^account$/i), 'a1')
    await waitFor(() => expect(listCardsSpy).toHaveBeenCalledWith('a1'))
    expect(screen.getByLabelText(/^card$/i)).toBeEnabled()
    await userEvent.selectOptions(screen.getByLabelText(/^card$/i), 'k1')
    await userEvent.type(screen.getByLabelText(/amount/i), '9')
    await userEvent.click(screen.getByRole('button', { name: /save/i }))
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    const payload = create.mock.calls[0][0]
    expect(payload).toMatchObject({ account_id: 'a1', card_id: 'k1', customer_id: 'c1', amount: 9 })
  })

  it('allows selecting a different currency from the list', async () => {
    vi.spyOn(acctApi, 'listAccounts').mockResolvedValue([acct] as never)
    const create = vi.spyOn(txnApi, 'createTransaction').mockResolvedValue({} as never)
    renderPage()
    await screen.findByRole('button', { name: /save/i })
    await userEvent.selectOptions(screen.getByLabelText(/^account$/i), 'a1')
    await userEvent.selectOptions(screen.getByLabelText(/^currency$/i), 'EUR')
    await userEvent.type(screen.getByLabelText(/amount/i), '15.00')
    await userEvent.click(screen.getByRole('button', { name: /save/i }))
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    const payload = create.mock.calls[0][0]
    expect(payload).toMatchObject({ account_id: 'a1', customer_id: 'c1', amount: 15, currency: 'EUR' })
  })

  it('sends the merchant fields when provided', async () => {
    vi.spyOn(acctApi, 'listAccounts').mockResolvedValue([acct] as never)
    const create = vi.spyOn(txnApi, 'createTransaction').mockResolvedValue({} as never)
    renderPage()
    await screen.findByRole('button', { name: /save/i })
    await userEvent.selectOptions(screen.getByLabelText(/^account$/i), 'a1')
    await userEvent.type(screen.getByLabelText(/amount/i), '12')
    await userEvent.type(screen.getByLabelText(/^merchant$/i), 'Starbucks')
    await userEvent.type(screen.getByLabelText(/merchant category/i), 'FOOD')
    await userEvent.type(screen.getByLabelText(/merchant city/i), 'Austin')
    await userEvent.type(screen.getByLabelText(/merchant state/i), 'TX')
    await userEvent.click(screen.getByRole('button', { name: /save/i }))
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    expect(create.mock.calls[0][0]).toMatchObject({
      merchant_name: 'Starbucks', merchant_category: 'FOOD', merchant_city: 'Austin', merchant_state: 'TX',
    })
  })
})
