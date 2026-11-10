import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/analytics'
import { ApiError } from '../api/client'
import type { DataAnalytics } from '../types/analytics'
import AnalyticsPage from './AnalyticsPage'

const sample: DataAnalytics = {
  source_mode: 'mock',
  generated_at: '2026-10-26T12:00:00Z',
  query_ms: 12.3,
  row_count: 10,
  total_customers: 10,
  total_accounts: 31,
  total_balance: 932001.5,
  total_transactions: 2146,
  total_txn_amount: 3124240,
  avg_balance_per_customer: 93200.15,
  avg_income: 52000,
  data_quality: { complete: 8, missing_email: 0, missing_phone: 2 },
  by_segment: [
    { label: 'RETAIL', count: 6 },
    { label: 'SMB', count: 4 },
  ],
  by_generation: [{ label: 'Millennial', count: 5 }],
  by_gender: [{ label: 'F', count: 5 }],
  by_country: [{ label: 'US', count: 10 }],
  balance_by_segment: [{ label: 'SMB', value: 743850 }],
}

afterEach(() => vi.restoreAllMocks())

function renderPage() {
  return render(
    <MemoryRouter>
      <AnalyticsPage />
    </MemoryRouter>,
  )
}

describe('AnalyticsPage', () => {
  it('renders KPI tiles and distributions from the snapshot', async () => {
    vi.spyOn(api, 'getC360Analytics').mockResolvedValue(sample)
    renderPage()

    expect(await screen.findByText('Data Analytics')).toBeInTheDocument()
    // KPI tiles with unambiguous values.
    expect(screen.getByText('Customers')).toBeInTheDocument()
    expect(screen.getByText('31')).toBeInTheDocument() // total accounts
    expect(screen.getByText('$52,000')).toBeInTheDocument() // avg income
    // Segment distribution bars (SMB also appears in the balance chart).
    expect(screen.getByText('RETAIL')).toBeInTheDocument()
    expect(screen.getAllByText('SMB').length).toBeGreaterThan(0)
    // Data-quality rollup.
    expect(screen.getByText('Missing phone')).toBeInTheDocument()
  })

  it('labels the snapshot source mode', async () => {
    vi.spyOn(api, 'getC360Analytics').mockResolvedValue(sample)
    renderPage()
    expect(await screen.findByText(/mock snapshot/i)).toBeInTheDocument()
  })

  it('shows the backend-measured snapshot query time', async () => {
    vi.spyOn(api, 'getC360Analytics').mockResolvedValue(sample)
    renderPage()
    expect(await screen.findByText(/snapshot query 12 ms/i)).toBeInTheDocument()
  })

  it('shows an empty state when the snapshot has no rows', async () => {
    vi.spyOn(api, 'getC360Analytics').mockResolvedValue({ ...sample, row_count: 0, source_mode: 'live' })
    renderPage()
    expect(await screen.findByText(/no profile rows/i)).toBeInTheDocument()
  })

  it('shows an error message when the request fails', async () => {
    vi.spyOn(api, 'getC360Analytics').mockRejectedValue(new ApiError(500, 'boom'))
    renderPage()
    expect(await screen.findByText(/boom/)).toBeInTheDocument()
  })

  it('refetches when Refresh is clicked', async () => {
    const spy = vi.spyOn(api, 'getC360Analytics').mockResolvedValue(sample)
    renderPage()
    await screen.findByText('Data Analytics')
    await userEvent.click(screen.getByRole('button', { name: /refresh/i }))
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2))
  })
})
