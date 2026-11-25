import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/accounts'
import * as cardsApi from '../api/cards'
import { ApiError } from '../api/client'
import AccountDetailPage from './AccountDetailPage'

const account = {
  account_id: 'a1', customer_id: 'c1', account_number: 'ACC-1', account_type: 'CHECKING',
  currency: 'USD', balance: 100, credit_limit: null, opened_date: '2021-01-01',
  closed_date: null, status: 'ACTIVE', created_at: '', updated_at: '',
}

const card = {
  card_id: 'k1', account_id: 'a1', card_brand: 'VISA', card_type: 'DEBIT',
  card_number: '4532010000079192', expires: '2027-01-28', has_chip: true,
  credit_limit: null, created_at: '', updated_at: '',
}

beforeEach(() => {
  vi.spyOn(cardsApi, 'listCards').mockResolvedValue([])
})

afterEach(() => vi.restoreAllMocks())

function renderAt(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/accounts/${id}`]}>
      <Routes><Route path="/accounts/:id" element={<AccountDetailPage />} /></Routes>
    </MemoryRouter>,
  )
}

describe('AccountDetailPage', () => {
  it('renders account fields', async () => {
    vi.spyOn(api, 'getAccount').mockResolvedValue(account as never)
    renderAt('a1')
    expect(await screen.findByRole('heading', { name: /ACC-1/ })).toBeInTheDocument()
    expect(screen.getByText('CHECKING')).toBeInTheDocument()
  })

  it('lists the account cards with a masked number', async () => {
    vi.spyOn(api, 'getAccount').mockResolvedValue(account as never)
    vi.spyOn(cardsApi, 'listCards').mockResolvedValue([card])
    renderAt('a1')
    expect(await screen.findByText('•••• 9192')).toBeInTheDocument()
    expect(screen.queryByText('4532010000079192')).not.toBeInTheDocument()
    expect(cardsApi.listCards).toHaveBeenCalledWith('a1')
  })

  it('shows an empty state when the account has no cards', async () => {
    vi.spyOn(api, 'getAccount').mockResolvedValue(account as never)
    renderAt('a1')
    expect(await screen.findByText(/No cards yet/)).toBeInTheDocument()
  })

  it('links Back to the owning customer', async () => {
    vi.spyOn(api, 'getAccount').mockResolvedValue(account as never)
    renderAt('a1')
    const back = await screen.findByRole('link', { name: /back/i })
    expect(back).toHaveAttribute('href', '/customers/c1')
  })

  it('shows the error message on 404', async () => {
    vi.spyOn(api, 'getAccount').mockRejectedValue(new ApiError(404, 'Account not found'))
    renderAt('nope')
    expect(await screen.findByText(/Account not found/)).toBeInTheDocument()
  })

  it('creates a card from the add-card icon and refreshes the list', async () => {
    vi.spyOn(api, 'getAccount').mockResolvedValue(account as never)
    const create = vi.spyOn(cardsApi, 'createCard').mockResolvedValue(card)
    const list = vi.spyOn(cardsApi, 'listCards').mockResolvedValueOnce([]).mockResolvedValue([card])
    renderAt('a1')
    await userEvent.click(await screen.findByRole('button', { name: /add card/i }))
    await userEvent.type(screen.getByLabelText(/card number/i), '4532010000079192')
    await userEvent.click(screen.getByRole('button', { name: /create card/i }))
    await waitFor(() => expect(create).toHaveBeenCalledWith(expect.objectContaining({
      account_id: 'a1', card_brand: 'VISA', card_type: 'DEBIT', card_number: '4532010000079192', credit_limit: null,
    })))
    expect(await screen.findByText('•••• 9192')).toBeInTheDocument()
    expect(list).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole('form', { name: /new card/i })).not.toBeInTheDocument()
  })

  it('rejects a malformed card number without calling the API', async () => {
    vi.spyOn(api, 'getAccount').mockResolvedValue(account as never)
    const create = vi.spyOn(cardsApi, 'createCard')
    renderAt('a1')
    await userEvent.click(await screen.findByRole('button', { name: /add card/i }))
    await userEvent.type(screen.getByLabelText(/card number/i), '12ab')
    await userEvent.click(screen.getByRole('button', { name: /create card/i }))
    expect(await screen.findByText(/12 to 19 digits/)).toBeInTheDocument()
    expect(create).not.toHaveBeenCalled()
  })
})
