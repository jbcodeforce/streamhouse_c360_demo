import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as customersApi from '../api/customers'
import * as accountsApi from '../api/accounts'
import { ApiError } from '../api/client'
import CustomerDetailPage from './CustomerDetailPage'

const customer = {
  customer_id: '1', first_name: 'Ada', last_name: 'Lovelace', email: 'ada@x.io',
  phone: '555', segment: 'VIP', status: 'ACTIVE', country: 'US',
  customer_since: '2020-01-01', created_at: '', updated_at: '',
}

const account = {
  account_id: 'a1', customer_id: '1', account_number: 'ACC-1', account_type: 'CHECKING',
  currency: 'USD', balance: 100, credit_limit: null, opened_date: '2021-01-01',
  closed_date: null, status: 'ACTIVE', created_at: '', updated_at: '',
}

afterEach(() => vi.restoreAllMocks())

function renderAt(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/customers/${id}`]}>
      <Routes>
        <Route path="/customers/:id" element={<CustomerDetailPage />} />
        <Route path="/accounts/new" element={<div>new account form</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('CustomerDetailPage', () => {
  it('renders the customer fields', async () => {
    vi.spyOn(customersApi, 'getCustomer').mockResolvedValue(customer as never)
    vi.spyOn(accountsApi, 'listAccounts').mockResolvedValue([] as never)
    renderAt('1')
    expect(await screen.findByText('ada@x.io')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Ada Lovelace/ })).toBeInTheDocument()
  })

  it('renders yearly income, retirement age and credit score', async () => {
    vi.spyOn(customersApi, 'getCustomer').mockResolvedValue(
      { ...customer, yearly_income: '78500.00', retirement_age: 65, credit_score: 742 } as never,
    )
    vi.spyOn(accountsApi, 'listAccounts').mockResolvedValue([] as never)
    renderAt('1')
    expect(await screen.findByText('$78,500')).toBeInTheDocument()
    expect(screen.getByText('65')).toBeInTheDocument()
    expect(screen.getByText('742')).toBeInTheDocument()
  })

  it('shows the error message on 404', async () => {
    vi.spyOn(customersApi, 'getCustomer').mockRejectedValue(new ApiError(404, 'Customer not found'))
    vi.spyOn(accountsApi, 'listAccounts').mockResolvedValue([] as never)
    renderAt('nope')
    expect(await screen.findByText(/Customer not found/)).toBeInTheDocument()
  })

  it('lists the accounts for this customer', async () => {
    vi.spyOn(customersApi, 'getCustomer').mockResolvedValue(customer as never)
    const list = vi.spyOn(accountsApi, 'listAccounts').mockResolvedValue([account] as never)
    renderAt('1')
    expect(await screen.findByText('ACC-1')).toBeInTheDocument()
    expect(list).toHaveBeenCalledWith('1')
  })

  it('shows an empty state when the customer has no accounts', async () => {
    vi.spyOn(customersApi, 'getCustomer').mockResolvedValue(customer as never)
    vi.spyOn(accountsApi, 'listAccounts').mockResolvedValue([] as never)
    renderAt('1')
    expect(await screen.findByText(/no accounts yet/i)).toBeInTheDocument()
  })

  it('links Add account to the prefilled new-account form', async () => {
    vi.spyOn(customersApi, 'getCustomer').mockResolvedValue(customer as never)
    vi.spyOn(accountsApi, 'listAccounts').mockResolvedValue([] as never)
    renderAt('1')
    const link = await screen.findByRole('link', { name: /add account/i })
    expect(link).toHaveAttribute('href', '/accounts/new?customer_id=1')
  })

  it('closes an account after confirmation and refetches', async () => {
    vi.spyOn(customersApi, 'getCustomer').mockResolvedValue(customer as never)
    const list = vi.spyOn(accountsApi, 'listAccounts')
    list
      .mockResolvedValueOnce([account] as never)
      .mockResolvedValueOnce([{ ...account, status: 'CLOSED' }] as never)
    const update = vi.spyOn(accountsApi, 'updateAccount').mockResolvedValue({} as never)
    renderAt('1')
    const row = (await screen.findByText('ACC-1')).closest('tr')!
    await userEvent.click(within(row).getByRole('button', { name: /close/i }))
    const dialog = screen.getByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: /^close$/i }))
    await waitFor(() => expect(update).toHaveBeenCalledWith('a1', { status: 'CLOSED' }))
    await waitFor(() => expect(screen.getByText('CLOSED')).toBeInTheDocument())
  })
})
