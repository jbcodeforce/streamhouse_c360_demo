import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import Sidebar from './Sidebar'

describe('Sidebar', () => {
  it('renders nav links for the three sections', () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: /customers/i })).toHaveAttribute('href', '/customers')
    expect(screen.getByRole('link', { name: /transactions/i })).toHaveAttribute(
      'href',
      '/transactions',
    )
  })

  it('has no standalone Accounts link (accounts live under a customer)', () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    )
    expect(screen.queryByRole('link', { name: /^accounts$/i })).toBeNull()
  })

  it('renders a Data Products link pointing to /data-products', () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: /data products/i })).toHaveAttribute(
      'href',
      '/data-products',
    )
  })

  it('renders an Analytics link pointing to /analytics', () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: /analytics/i })).toHaveAttribute('href', '/analytics')
  })

  it('renders a Scenarios link pointing to /scenarios and no CEP Patterns link', () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: /scenarios/i })).toHaveAttribute('href', '/scenarios')
    expect(screen.queryByRole('link', { name: /cep patterns/i })).toBeNull()
  })
})
