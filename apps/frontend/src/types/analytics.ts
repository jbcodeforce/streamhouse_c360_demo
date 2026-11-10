export interface CategoryCount {
  label: string
  count: number
}

export interface CategoryValue {
  label: string
  value: number
}

export interface DataQuality {
  complete: number
  missing_email: number
  missing_phone: number
}

export interface DataAnalytics {
  source_mode: string
  generated_at: string
  query_ms: number
  row_count: number

  total_customers: number
  total_accounts: number
  total_balance: number
  total_transactions: number
  total_txn_amount: number

  avg_balance_per_customer: number | null
  avg_income: number | null

  data_quality: DataQuality

  by_segment: CategoryCount[]
  by_generation: CategoryCount[]
  by_gender: CategoryCount[]
  by_country: CategoryCount[]
  balance_by_segment: CategoryValue[]
}

export interface CustomerProfile {
  source_mode: string
  query_ms: number
  customer_id: string
  first_name: string | null
  last_name: string | null
  customer_segment: string | null
  generation_segment: string | null
  gender: string | null
  city: string | null
  state: string | null
  country: string | null
  customer_since: string | null
  days_since_registration: number | null
  missing_email_flag: number | null
  missing_phone_flag: number | null
  account_count: number
  total_balance: number
  txn_count: number
  txn_total: number
}
