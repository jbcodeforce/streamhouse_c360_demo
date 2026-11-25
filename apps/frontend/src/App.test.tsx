import { render, screen } from '@testing-library/react'
import { MemoryRouter, Outlet } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from './App'

vi.mock('./components/AppLayout', () => ({ default: () => <Outlet /> }))
vi.mock('./pages/ScenariosPage', () => ({ default: () => <h1>Scenarios page</h1> }))

describe('App routing', () => {
  it('renders the Scenarios page at /scenarios', () => {
    render(
      <MemoryRouter initialEntries={['/scenarios']}>
        <App />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: 'Scenarios page' })).toBeInTheDocument()
  })

  it('redirects the legacy /cep route to /scenarios', () => {
    render(
      <MemoryRouter initialEntries={['/cep']}>
        <App />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: 'Scenarios page' })).toBeInTheDocument()
  })
})
