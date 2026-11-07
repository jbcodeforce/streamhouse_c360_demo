export interface Card {
  card_id: string
  account_id: string
  card_brand: string
  card_type: string
  card_number: string
  expires: string
  has_chip: boolean
  credit_limit: number | string | null
  created_at: string
  updated_at: string
}
