import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as txnApi from '../api/transactions'
import * as acctApi from '../api/accounts'
import * as custApi from '../api/customers'
import * as cardsApi from '../api/cards'
import { ApiError } from '../api/client'
import TransactionsPage from './TransactionsPage'

const txn = {
  transaction_id: 't1', account_id: 'a1', customer_id: 'c1', transaction_type: 'CREDIT',
  amount: 99.9, currency: 'USD', status: 'COMPLETED', transacted_at: '2024-01-01T00:00:00+00:00',
  posted_at: null, created_at: '',
}
const acct = { account_id: 'a1', customer_id: 'c1', account_number: 'CHK-1', account_type: 'CHECKING', currency: 'USD', balance: 0, credit_limit: null, opened_date: '2020-01-01', closed_date: null, status: 'ACTIVE', created_at: '', updated_at: '' }
const cust = { customer_id: 'c1', first_name: 'Ada', last_name: 'Lovelace', email: 'a@x.io', country: 'US', customer_since: '2020-01-01', created_at: '', updated_at: '' }

const card = { card_id: 'k1', account_id: 'a1', card_brand: 'VISA', card_type: 'DEBIT', card_number: '4532010000079192', expires: '2027-01-28', has_chip: true, credit_limit: null, created_at: '', updated_at: '' }

beforeEach(() => {
  vi.spyOn(cardsApi, 'listCards').mockResolvedValue([card] as never)
})
afterEach(() => vi.restoreAllMocks())

describe('TransactionsPage', () => {
  it('renders rows with resolved account number and customer name', async () => {
    vi.spyOn(txnApi, 'listTransactions').mockResolvedValue([txn] as never)
    vi.spyOn(acctApi, 'listAccounts').mockResolvedValue([acct] as never)
    vi.spyOn(custApi, 'listCustomers').mockResolvedValue([cust] as never)
    render(<MemoryRouter><TransactionsPage /></MemoryRouter>)
    expect(await screen.findByText('CHK-1')).toBeInTheDocument()
    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument()
    expect(screen.getByText('CREDIT')).toBeInTheDocument()
  })

  it('renders merchant name and category columns', async () => {
    vi.spyOn(txnApi, 'listTransactions').mockResolvedValue(
      [{ ...txn, merchant_name: 'Amazon', merchant_category: 'RETAIL' }] as never,
    )
    vi.spyOn(acctApi, 'listAccounts').mockResolvedValue([acct] as never)
    vi.spyOn(custApi, 'listCustomers').mockResolvedValue([cust] as never)
    render(<MemoryRouter><TransactionsPage /></MemoryRouter>)
    expect(await screen.findByText('Amazon')).toBeInTheDocument()
    expect(screen.getByText('RETAIL')).toBeInTheDocument()
  })

  it('renders a card-only transaction with a masked card and no account', async () => {
    vi.spyOn(txnApi, 'listTransactions').mockResolvedValue(
      [{ ...txn, account_id: null, card_id: 'k1' }] as never,
    )
    vi.spyOn(acctApi, 'listAccounts').mockResolvedValue([acct] as never)
    vi.spyOn(custApi, 'listCustomers').mockResolvedValue([cust] as never)
    render(<MemoryRouter><TransactionsPage /></MemoryRouter>)
    expect(await screen.findByText('•••• 9192')).toBeInTheDocument()
    expect(screen.queryByText('CHK-1')).not.toBeInTheDocument()
  })

  it('shows an error when the list request fails', async () => {
    vi.spyOn(txnApi, 'listTransactions').mockRejectedValue(new ApiError(500, 'boom'))
    vi.spyOn(acctApi, 'listAccounts').mockResolvedValue([] as never)
    vi.spyOn(custApi, 'listCustomers').mockResolvedValue([] as never)
    render(<MemoryRouter><TransactionsPage /></MemoryRouter>)
    expect(await screen.findByText(/boom/)).toBeInTheDocument()
  })

  describe('generate button', () => {
    function mockLists() {
      vi.spyOn(txnApi, 'listTransactions').mockResolvedValue([txn] as never)
      vi.spyOn(acctApi, 'listAccounts').mockResolvedValue([acct] as never)
      vi.spyOn(custApi, 'listCustomers').mockResolvedValue([cust] as never)
    }

    function StateProbe() {
      const { state } = useLocation()
      return <div>generated: {(state as { transactions: unknown[] }).transactions.length}</div>
    }

    function renderWithRoutes() {
      return render(
        <MemoryRouter initialEntries={['/transactions']}>
          <Routes>
            <Route path="/transactions" element={<TransactionsPage />} />
            <Route path="/transactions/generated" element={<StateProbe />} />
          </Routes>
        </MemoryRouter>,
      )
    }

    it('calls the API, disables while pending, then navigates with the result as state', async () => {
      mockLists()
      let resolve!: (v: unknown[]) => void
      const gen = vi.spyOn(txnApi, 'generateTransactions').mockReturnValue(
        new Promise((r) => { resolve = r as never }),
      )
      renderWithRoutes()
      await screen.findByText('CHK-1')

      await userEvent.click(screen.getByRole('button', { name: /generate 200 transactions/i }))
      expect(gen).toHaveBeenCalledTimes(1)
      expect(await screen.findByRole('button', { name: /generating/i })).toBeDisabled()

      resolve([txn, txn])
      expect(await screen.findByText('generated: 2')).toBeInTheDocument()
    })

    it('shows an error and re-enables the button when generation fails', async () => {
      mockLists()
      vi.spyOn(txnApi, 'generateTransactions').mockRejectedValue(
        new ApiError(409, 'No active accounts available'),
      )
      renderWithRoutes()
      await screen.findByText('CHK-1')

      await userEvent.click(screen.getByRole('button', { name: /generate 200 transactions/i }))
      expect(await screen.findByText(/No active accounts available/)).toBeInTheDocument()
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /generate 200 transactions/i })).toBeEnabled(),
      )
      expect(screen.getByText('CHK-1')).toBeInTheDocument() // table stays visible
    })
  })
})
