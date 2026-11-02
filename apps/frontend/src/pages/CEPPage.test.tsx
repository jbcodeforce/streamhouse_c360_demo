import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/scenarios'
import { ApiError } from '../api/client'
import CEPPage from './CEPPage'
import type { ScenarioDefinition, ScenarioResult } from '../types/scenario'

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

function renderPage() {
  return render(
    <MemoryRouter>
      <CEPPage />
    </MemoryRouter>,
  )
}

describe('CEPPage', () => {
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
