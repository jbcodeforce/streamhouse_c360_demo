import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
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
})
