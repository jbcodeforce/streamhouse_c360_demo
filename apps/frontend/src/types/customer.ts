export interface CustomerCreate {
  first_name: string
  last_name: string
  email: string
  phone?: string | null
  date_of_birth?: string | null // ISO date/datetime string
  gender?: string | null
  address_line1?: string | null
  address_line2?: string | null
  city?: string | null
  state?: string | null
  postal_code?: string | null
  country?: string | null // backend defaults to "US"
  customer_since?: string | null // ISO date; backend defaults to today
  segment?: string | null
  status?: string | null // backend defaults to "ACTIVE"
  per_capita_income?: number | string | null // decimal(18,2); API may return a string
  retirement_age?: number | null
}

export type CustomerUpdate = Partial<CustomerCreate>

export interface Customer extends CustomerCreate {
  customer_id: string
  created_at: string
  updated_at: string
}
