export interface TransactionCreate {
  // A transaction has an account, a card, or both.
  account_id?: string | null
  customer_id: string
  transaction_type: string
  amount: number
  currency?: string | null
  description?: string | null
  merchant_name?: string | null
  merchant_category?: string | null
  channel?: string | null
  status?: string | null
  transacted_at?: string | null
  posted_at?: string | null
  card_id?: string | null
  use_chip?: string | null
  merchant_city?: string | null
  merchant_state?: string | null
  zip?: string | null
}

export interface Transaction extends TransactionCreate {
  transaction_id: string
  created_at: string
}
