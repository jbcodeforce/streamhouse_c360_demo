import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as accountsApi from '../api/accounts'
import * as customersApi from '../api/customers'
import AccountFormPage from './AccountFormPage'

const customer = {
  customer_id: 'c1', first_name: 'Ada', last_name: 'Lovelace', email: 'ada@x.io',
  country: 'US', customer_since: '2020-01-01', created_at: '', updated_at: '',
}

afterEach(() => vi.restoreAllMocks())

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/accounts/new" element={<AccountFormPage />} />
        <Route path="/accounts/:accountId/edit" element={<AccountFormPage />} />
        <Route path="/customers/:id" element={<div>customer page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('AccountFormPage', () => {
  it('validates required fields before submitting', async () => {
    vi.spyOn(customersApi, 'listCustomers').mockResolvedValue([customer] as never)
    const create = vi.spyOn(accountsApi, 'createAccount').mockResolvedValue({} as never)
    renderAt('/accounts/new?customer_id=c1')
    await screen.findByRole('button', { name: /save/i })
    await userEvent.click(screen.getByRole('button', { name: /save/i }))
    expect(await screen.findByText(/account number is required/i)).toBeInTheDocument()
    expect(create).not.toHaveBeenCalled()
  })

  it('prefills and locks the customer from the query param, then returns to the customer page', async () => {
    vi.spyOn(customersApi, 'listCustomers').mockResolvedValue([customer] as never)
    const create = vi.spyOn(accountsApi, 'createAccount').mockResolvedValue({} as never)
    renderAt('/accounts/new?customer_id=c1')
    const select = (await screen.findByLabelText(/customer/i)) as HTMLSelectElement
    expect(select.value).toBe('c1')
    expect(select).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/account number/i), 'ACC-1')
    await userEvent.click(screen.getByRole('button', { name: /save/i }))
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    expect(create.mock.calls[0][0]).toMatchObject({ customer_id: 'c1', account_number: 'ACC-1' })
    expect(await screen.findByText('customer page')).toBeInTheDocument()
  })

  it('loads an existing account and updates via PUT in edit mode', async () => {
    vi.spyOn(customersApi, 'listCustomers').mockResolvedValue([customer] as never)
    vi.spyOn(accountsApi, 'getAccount').mockResolvedValue({
      account_id: 'a1', customer_id: 'c1', account_number: 'ACC-1', account_type: 'CHECKING',
      currency: 'USD', balance: 50, credit_limit: null, opened_date: '2021-01-01',
      closed_date: null, status: 'ACTIVE', created_at: '', updated_at: '',
    } as never)
    const update = vi.spyOn(accountsApi, 'updateAccount').mockResolvedValue({} as never)
    const create = vi.spyOn(accountsApi, 'createAccount')
    renderAt('/accounts/a1/edit')
    expect(await screen.findByDisplayValue('ACC-1')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText(/status/i), 'CLOSED')
    await userEvent.click(screen.getByRole('button', { name: /save/i }))
    await waitFor(() => expect(update).toHaveBeenCalledWith('a1', expect.objectContaining({ status: 'CLOSED' })))
    expect(create).not.toHaveBeenCalled()
    expect(await screen.findByText('customer page')).toBeInTheDocument()
  })
})
