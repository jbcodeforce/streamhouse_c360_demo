import type { Card } from '../types/card'
import { request } from './client'

// Lists the cards of one account, or all cards when no account is given.
export function listCards(accountId?: string): Promise<Card[]> {
  const query = accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''
  return request<Card[]>(`/cards${query}`)
}
