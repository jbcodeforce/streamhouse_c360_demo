import type { Transaction, TransactionCreate } from '../types/transaction'
import { request } from './client'

export function listTransactions(): Promise<Transaction[]> {
  return request<Transaction[]>('/transactions')
}

export function getTransaction(id: string): Promise<Transaction> {
  return request<Transaction>(`/transactions/${id}`)
}

export function createTransaction(data: TransactionCreate): Promise<Transaction> {
  return request<Transaction>('/transactions', { method: 'POST', body: JSON.stringify(data) })
}

export interface GenerateTransactionsOptions {
  customerId?: string
  count?: number
}

export function generateTransactions(options?: GenerateTransactionsOptions): Promise<Transaction[]> {
  const searchParams = new URLSearchParams()
  if (options?.customerId) {
    searchParams.set('customer_id', options.customerId)
  }
  if (options?.count !== undefined) {
    searchParams.set('count', String(options.count))
  }
  const qs = searchParams.toString()
  return request<Transaction[]>(qs ? `/transactions/generate?${qs}` : '/transactions/generate', {
    method: 'POST',
  })
}
