import type { Card } from '../types/card'
import { request } from './client'

export function listCards(accountId: string): Promise<Card[]> {
  return request<Card[]>(`/cards?account_id=${encodeURIComponent(accountId)}`)
}
