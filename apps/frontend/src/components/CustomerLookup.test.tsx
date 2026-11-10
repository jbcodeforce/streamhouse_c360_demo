import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import type { CustomerProfile } from '../types/analytics'
import type { Customer } from '../types/customer'
import CustomerLookup from './CustomerLookup'

/** Build a minimal Customer for the picker/search results. */
function cust(partial: Partial<Customer> & Pick<Customer, 'customer_id' | 'first_name' | 'last_name'>): Customer {
  return {
    email: 'x@example.com',
    created_at: '2020-01-01T00:00:00Z',
    updated_at: '2020-01-01T00:00:00Z',
    ...partial,
  }
}

const thomas: CustomerProfile = {
  source_mode: 'mock',
  query_ms: 7.4,
  customer_id: 'id-thomas',
  first_name: 'Thomas',
  last_name: 'Brennan',
  customer_segment: 'SMB',
  generation_segment: 'Boomer+',
  gender: 'M',
  city: 'Seattle',
  state: 'WA',
  country: 'US',
  customer_since: '2017-12-01',
  days_since_registration: 3251,
  missing_email_flag: 0,
  missing_phone_flag: 0,
  account_count: 6,
  total_balance: 318400,
  txn_count: 512,
  txn_total: 1024700,
}

function renderLookup(
  search: (name: string) => Promise<Customer[]>,
  getProfile: (id: string) => Promise<CustomerProfile>,
) {
  return render(
    <CustomerLookup title="Customer lookup" subtitle="sub" badge="Test" search={search} getProfile={getProfile} />,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('CustomerLookup', () => {
  it('renders the title and engine badge', () => {
    renderLookup(vi.fn(), vi.fn())
    expect(screen.getByText('Customer lookup')).toBeInTheDocument()
    expect(screen.getByText('Test')).toBeInTheDocument()
  })

  it('auto-loads the profile when exactly one customer matches', async () => {
    const search = vi.fn().mockResolvedValue([
      cust({ customer_id: 'id-thomas', first_name: 'Thomas', last_name: 'Brennan', segment: 'SMB', city: 'Seattle', state: 'WA' }),
    ])
    const getProfile = vi.fn().mockResolvedValue(thomas)

    renderLookup(search, getProfile)
    await userEvent.type(screen.getByLabelText(/customer name/i), 'brennan')
    await userEvent.click(screen.getByRole('button', { name: /search/i }))

    await waitFor(() => expect(getProfile).toHaveBeenCalledWith('id-thomas'))
    expect(await screen.findByText('Thomas Brennan')).toBeInTheDocument()
    expect(screen.getByText('$318,400')).toBeInTheDocument()
    expect(screen.getByText('512')).toBeInTheDocument()
    // The only query timer shown is the analytics point-lookup time.
    expect(screen.getByText(/lookup 7.4 ms/i)).toBeInTheDocument()
  })

  it('shows a picker when multiple customers match and loads the chosen one', async () => {
    const search = vi.fn().mockResolvedValue([
      cust({ customer_id: 'id-a', first_name: 'Linda', last_name: 'Sharma', segment: 'SMB', city: 'Austin', state: 'TX' }),
      cust({ customer_id: 'id-thomas', first_name: 'Thomas', last_name: 'Brennan', segment: 'SMB', city: 'Seattle', state: 'WA' }),
    ])
    const getProfile = vi.fn().mockResolvedValue(thomas)

    renderLookup(search, getProfile)
    await userEvent.type(screen.getByLabelText(/customer name/i), 'a')
    await userEvent.click(screen.getByRole('button', { name: /search/i }))

    expect(await screen.findByText('Linda Sharma')).toBeInTheDocument()
    expect(getProfile).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: /thomas brennan/i }))
    await waitFor(() => expect(getProfile).toHaveBeenCalledWith('id-thomas'))
    expect(await screen.findByText('Boomer+')).toBeInTheDocument()
  })

  it('shows a no-match message when nothing is found', async () => {
    renderLookup(vi.fn().mockResolvedValue([]), vi.fn())
    await userEvent.type(screen.getByLabelText(/customer name/i), 'zzz')
    await userEvent.click(screen.getByRole('button', { name: /search/i }))
    expect(await screen.findByText(/no customers match/i)).toBeInTheDocument()
  })

  it('shows an error when the search request fails', async () => {
    renderLookup(vi.fn().mockRejectedValue(new ApiError(500, 'search boom')), vi.fn())
    await userEvent.type(screen.getByLabelText(/customer name/i), 'x')
    await userEvent.click(screen.getByRole('button', { name: /search/i }))
    expect(await screen.findByText(/search boom/)).toBeInTheDocument()
  })

  it('searchProfiles: one call resolves name to profiles without a second by-id call', async () => {
    const searchProfiles = vi.fn().mockResolvedValue([thomas])
    const getProfile = vi.fn()
    render(
      <CustomerLookup title="Customer lookup" subtitle="sub" searchProfiles={searchProfiles} getProfile={getProfile} />,
    )
    await userEvent.type(screen.getByLabelText(/customer name/i), 'brennan')
    await userEvent.click(screen.getByRole('button', { name: /search/i }))

    expect(await screen.findByText('Thomas Brennan')).toBeInTheDocument()
    expect(screen.getByText('$318,400')).toBeInTheDocument()
    expect(searchProfiles).toHaveBeenCalledWith('brennan')
    expect(getProfile).not.toHaveBeenCalled()
  })
})
