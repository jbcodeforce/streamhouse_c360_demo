import type { ScenarioDefinition, ScenarioResult } from '../types/scenario'
import { request } from './client'

export function listScenarios(): Promise<ScenarioDefinition[]> {
  return request<ScenarioDefinition[]>('/scenarios')
}

export function runScenario(scenarioId: string): Promise<ScenarioResult> {
  return request<ScenarioResult>(`/scenarios/${scenarioId}/run`, { method: 'POST' })
}
