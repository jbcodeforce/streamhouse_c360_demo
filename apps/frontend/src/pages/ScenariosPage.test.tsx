import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/scenarios'
import * as txnApi from '../api/transactions'
import { ApiError } from '../api/client'
import ScenariosPage from './ScenariosPage'
import type { ScenarioDefinition, ScenarioResult } from '../types/scenario'
import type { Transaction } from '../types/transaction'

afterEach(() => vi.restoreAllMocks())

const _SCENARIOS: ScenarioDefinition[] = [
  { scenario_id: 'fraud-probe',     pattern: 'fct_fraud_probe',     label: 'Fraud Probe',     description: 'Card probe desc' },
  { scenario_id: 'merchant-streak', pattern: 'fct_merchant_streak', label: 'Merchant Streak', description: 'Streak desc'     },
  { scenario_id: 'smb-spike',       pattern: 'fct_smb_spike',       label: 'SMB Spike',       description: 'SMB desc'        },
]

const _RESULT: ScenarioResult = {
  scenario_id: 'fraud-probe',
  pattern: 'fct_fraud_probe',
  label: 'Fraud Probe',
  triggered_at: '2026-11-01T12:00:00Z',
  transactions: [
    {
      transaction_id: 'tid-1',
      account_id: 'acct-1',
      customer_id: 'cust-1',
      transaction_type: 'DEBIT',
      amount: 2.99,
      currency: 'USD',
      description: 'Card verification',
      merchant_name: 'Amazon',
      merchant_category: 'RETAIL',
      channel: 'ONLINE',
      status: 'COMPLETED',
      transacted_at: '2026-11-01T12:00:00Z',
      posted_at: '2026-11-01T12:00:00Z',
      created_at: '2026-11-01T12:00:00Z',
    },
  ],
}

const _CARTER_ID = '00000000-0000-0000-0000-ef1234567890'

const _GENERATED: Transaction[] = [1, 2].map((n) => ({
  ..._RESULT.transactions[0],
  transaction_id: `gen-${n}`,
  amount: 10 * n,
  merchant_name: `Shop ${n}`,
}))

function renderPage() {
  return render(
    <MemoryRouter>
      <ScenariosPage />
    </MemoryRouter>,
  )
}

function StateProbe() {
  const { state } = useLocation()
  return <div>generated: {(state as { transactions: unknown[] }).transactions.length}</div>
}

function renderWithRoutes() {
  return render(
    <MemoryRouter initialEntries={['/scenarios']}>
      <Routes>
        <Route path="/scenarios" element={<ScenariosPage />} />
        <Route path="/transactions/generated" element={<StateProbe />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ScenariosPage generation scenarios', () => {
  function mockCep() {
    vi.spyOn(api, 'listScenarios').mockResolvedValue(_SCENARIOS)
  }

  it('renders the page title and both sections', async () => {
    mockCep()
    renderPage()
    expect(screen.getByRole('heading', { name: 'Scenarios', level: 1 })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Transaction generation' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Complex Event Processing' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create 200 transactions' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create transactions for Mr Carter' })).toBeInTheDocument()
    expect(await screen.findAllByText('Fraud Probe')).not.toHaveLength(0)
  })

  it('runs the 200 scenario with no options, disables while pending and shows a summary', async () => {
    mockCep()
    let resolve!: (v: Transaction[]) => void
    const gen = vi.spyOn(txnApi, 'generateTransactions').mockReturnValue(
      new Promise((r) => { resolve = r }),
    )
    renderPage()

    await userEvent.click(screen.getByRole('button', { name: 'Create 200 transactions' }))
    expect(gen).toHaveBeenCalledTimes(1)
    expect(gen).toHaveBeenCalledWith(undefined)
    expect(await screen.findByRole('button', { name: /generating/i })).toBeDisabled()

    resolve(_GENERATED)
    expect(await screen.findByText(/2 transactions written/)).toBeInTheDocument()
    expect(screen.getByText('Shop 1')).toBeInTheDocument()
    expect(screen.getByText('$20.00')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'View generated transactions' })).toBeInTheDocument()
  })

  it('runs the Carter scenario with customerId and count 20', async () => {
    mockCep()
    const gen = vi.spyOn(txnApi, 'generateTransactions').mockResolvedValue(_GENERATED)
    renderPage()

    await userEvent.click(screen.getByRole('button', { name: 'Create transactions for Mr Carter' }))
    expect(gen).toHaveBeenCalledWith({ customerId: _CARTER_ID, count: 20 })
    expect(await screen.findByText(/2 transactions written/)).toBeInTheDocument()
  })

  it('limits the inline table to a short preview of large batches', async () => {
    mockCep()
    const many = Array.from({ length: 200 }, (_, i) => ({
      ..._GENERATED[0], transaction_id: `g-${i}`, merchant_name: `Shop ${i}`,
    }))
    vi.spyOn(txnApi, 'generateTransactions').mockResolvedValue(many)
    renderPage()

    await userEvent.click(screen.getByRole('button', { name: 'Create 200 transactions' }))
    expect(await screen.findByText(/200 transactions written/)).toBeInTheDocument()
    const card = screen.getByRole('region', { name: 'Create 200 transactions' })
    expect(within(card).getAllByRole('row')).toHaveLength(1 + 5) // header + preview rows
    expect(within(card).getByText(/first 5 of 200/)).toBeInTheDocument()
  })

  it('shows an error (409) and re-enables the button when generation fails', async () => {
    mockCep()
    vi.spyOn(txnApi, 'generateTransactions').mockRejectedValue(
      new ApiError(409, 'No active accounts available'),
    )
    renderPage()

    await userEvent.click(screen.getByRole('button', { name: 'Create transactions for Mr Carter' }))
    expect(await screen.findByText(/No active accounts available/)).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Create transactions for Mr Carter' })).toBeEnabled(),
    )
    expect(screen.queryByRole('button', { name: 'View generated transactions' })).not.toBeInTheDocument()
  })

  it('falls back to a generic message for non-API errors', async () => {
    mockCep()
    vi.spyOn(txnApi, 'generateTransactions').mockRejectedValue(new Error('network'))
    renderPage()

    await userEvent.click(screen.getByRole('button', { name: 'Create 200 transactions' }))
    expect(await screen.findByText('Failed to generate transactions')).toBeInTheDocument()
  })

  it('navigates to /transactions/generated with the created transactions as state', async () => {
    mockCep()
    vi.spyOn(txnApi, 'generateTransactions').mockResolvedValue(_GENERATED)
    renderWithRoutes()

    await userEvent.click(screen.getByRole('button', { name: 'Create 200 transactions' }))
    await userEvent.click(await screen.findByRole('button', { name: 'View generated transactions' }))
    expect(await screen.findByText('generated: 2')).toBeInTheDocument()
  })
})

describe('ScenariosPage CEP section', () => {
  it('renders three pattern cards', async () => {
    vi.spyOn(api, 'listScenarios').mockResolvedValue(_SCENARIOS)
    renderPage()
    // Three cards render; the first is also shown in the detail panel so use getAllByText
    expect(await screen.findAllByText('Fraud Probe')).not.toHaveLength(0)
    expect(screen.getByText('Merchant Streak')).toBeInTheDocument()
    expect(screen.getByText('SMB Spike')).toBeInTheDocument()
  })

  it('shows an error when list request fails', async () => {
    vi.spyOn(api, 'listScenarios').mockRejectedValue(new ApiError(500, 'service unavailable'))
    renderPage()
    expect(await screen.findByText(/service unavailable/)).toBeInTheDocument()
  })

  it('calls runScenario and displays injected transactions on trigger', async () => {
    vi.spyOn(api, 'listScenarios').mockResolvedValue(_SCENARIOS)
    vi.spyOn(api, 'runScenario').mockResolvedValue(_RESULT)
    renderPage()
    // Wait for the detail panel heading (h2) to confirm the page has loaded
    expect(await screen.findByRole('heading', { name: 'Fraud Probe', level: 2 })).toBeInTheDocument()

    const btn = screen.getByRole('button', { name: /trigger scenario/i })
    await userEvent.click(btn)

    expect(api.runScenario).toHaveBeenCalledWith('fraud-probe')
    expect(await screen.findByText('$2.99')).toBeInTheDocument()
    expect(screen.getByText('Amazon')).toBeInTheDocument()
  })

  it('shows error message when trigger fails', async () => {
    vi.spyOn(api, 'listScenarios').mockResolvedValue(_SCENARIOS)
    vi.spyOn(api, 'runScenario').mockRejectedValue(new ApiError(409, 'Scenarios require SINK=postgres'))
    renderPage()
    expect(await screen.findByRole('heading', { name: 'Fraud Probe', level: 2 })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /trigger scenario/i }))
    expect(await screen.findByText(/SINK=postgres/)).toBeInTheDocument()
  })
})
