import type { Card, CardCreate, CardUpdate } from '../types/card'
import { request } from './client'

// Lists the cards of one account, or all cards when no account is given.
export function listCards(accountId?: string): Promise<Card[]> {
  const query = accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''
  return request<Card[]>(`/cards${query}`)
}

export function createCard(data: CardCreate): Promise<Card> {
  return request<Card>('/cards', { method: 'POST', body: JSON.stringify(data) })
}

export function updateCard(id: string, data: CardUpdate): Promise<Card> {
  return request<Card>(`/cards/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}
