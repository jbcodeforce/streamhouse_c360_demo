import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as acctApi from '../api/accounts'
import * as custApi from '../api/customers'
import * as cardsApi from '../api/cards'
import GeneratedTransactionsPage from './GeneratedTransactionsPage'

const mk = (id: string, at: string, amount: number) => ({
  transaction_id: id, account_id: 'a1', customer_id: 'c1', transaction_type: 'DEBIT',
  amount, currency: 'USD', status: 'COMPLETED', transacted_at: at,
  posted_at: at, created_at: '',
})
const acct = { account_id: 'a1', customer_id: 'c1', account_number: 'CHK-1', account_type: 'CHECKING', currency: 'USD', balance: 0, credit_limit: null, opened_date: '2020-01-01', closed_date: null, status: 'ACTIVE', created_at: '', updated_at: '' }
const cust = { customer_id: 'c1', first_name: 'Ada', last_name: 'Lovelace', email: 'a@x.io', country: 'US', customer_since: '2020-01-01', created_at: '', updated_at: '' }

beforeEach(() => {
  vi.spyOn(cardsApi, 'listCards').mockResolvedValue([] as never)
})
afterEach(() => vi.restoreAllMocks())

describe('GeneratedTransactionsPage', () => {
  it('renders the transactions passed via router state, newest first', async () => {
    vi.spyOn(acctApi, 'listAccounts').mockResolvedValue([acct] as never)
    vi.spyOn(custApi, 'listCustomers').mockResolvedValue([cust] as never)
    const transactions = [
      mk('t1', '2026-10-15T10:00:00+00:00', 11),
      mk('t2', '2026-10-15T10:15:00+00:00', 22),
    ]
    render(
      <MemoryRouter initialEntries={[{ pathname: '/transactions/generated', state: { transactions } }]}>
        <GeneratedTransactionsPage />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: /Generated transactions \(2\)/ })).toBeInTheDocument()
    expect((await screen.findAllByText('CHK-1')).length).toBe(2)
    expect(screen.getAllByText('Ada Lovelace').length).toBe(2)
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows).toHaveLength(2)
    // newest (t2, 10:15, amount 22) is listed before oldest (t1, 10:00, amount 11)
    expect(rows[0]).toHaveTextContent('22 USD')
    expect(rows[1]).toHaveTextContent('11 USD')
  })

  it('shows an empty state without router state (e.g. after refresh)', () => {
    render(
      <MemoryRouter initialEntries={['/transactions/generated']}>
        <GeneratedTransactionsPage />
      </MemoryRouter>,
    )
    expect(screen.getByText(/No generated transactions to display/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /back to transactions/i })).toHaveAttribute('href', '/transactions')
  })
})
