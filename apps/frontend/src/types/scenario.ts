import type { Transaction } from './transaction'

export interface ScenarioDefinition {
  scenario_id: string
  pattern: string
  label: string
  description: string
}

export interface ScenarioResult {
  scenario_id: string
  pattern: string
  label: string
  triggered_at: string
  transactions: Transaction[]
}
