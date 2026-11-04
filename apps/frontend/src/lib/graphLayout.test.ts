import { describe, expect, it } from 'vitest'
import type { GraphEdge, GraphNode } from '../types/dataProduct'
import { layoutGraph } from './graphLayout'

describe('layoutGraph', () => {
  it('places a source upstream (smaller x) of the statement it feeds', () => {
    const nodes = [
      { id: 'topic_customers', type: 'source', label: '' },
      { id: 'src_customers', type: 'statement', label: '' },
    ] as GraphNode[]
    const edges: GraphEdge[] = [{ source: 'topic_customers', target: 'src_customers' }]
    const pos = Object.fromEntries(layoutGraph(nodes, edges).map((n) => [n.id, n.position]))
    expect(pos.topic_customers.x).toBeLessThan(pos.src_customers.x)
  })

  it('returns a position for every node', () => {
    const nodes = [
      { id: 'topic_customers', type: 'source', label: '' },
      { id: 'topic_accounts', type: 'source', label: '' },
      { id: 'src_customers', type: 'statement', label: '' },
      { id: 'src_accounts', type: 'statement', label: '' },
      { id: 'int_c360', type: 'statement', label: '' },
    ] as GraphNode[]
    const edges: GraphEdge[] = [
      { source: 'topic_customers', target: 'src_customers' },
      { source: 'topic_accounts', target: 'src_accounts' },
      { source: 'src_customers', target: 'int_c360' },
      { source: 'src_accounts', target: 'int_c360' },
    ]
    const result = layoutGraph(nodes, edges)
    expect(result).toHaveLength(nodes.length)
    for (const node of nodes) {
      const entry = result.find((n) => n.id === node.id)
      expect(entry).toBeDefined()
      expect(typeof entry?.position.x).toBe('number')
      expect(typeof entry?.position.y).toBe('number')
    }
  })

  it('puts every product node in the right-most column without overlaps', () => {
    const n = (id: string, type: 'source' | 'statement', is_product = false) =>
      ({ id, type, label: id, is_product }) as GraphNode
    const nodes = [
      n('topic_accounts', 'source'),
      n('topic_customers', 'source'),
      n('topic_transactions', 'source'),
      n('src_accounts', 'statement'),
      n('src_customers', 'statement'),
      n('src_transactions', 'statement'),
      n('dim_transactions', 'statement'),
      n('dim_customers', 'statement'),
      n('dim_account_tx_agg', 'statement'),
      n('dim_tx_x_account', 'statement'),
      n('fct_merchant_streak', 'statement', true),
      n('fct_c360_profile', 'statement', true),
    ]
    const edges: GraphEdge[] = [
      ['topic_accounts', 'src_accounts'],
      ['topic_customers', 'src_customers'],
      ['topic_transactions', 'src_transactions'],
      ['src_transactions', 'dim_transactions'],
      ['src_customers', 'dim_customers'],
      ['src_accounts', 'dim_account_tx_agg'],
      ['dim_transactions', 'dim_account_tx_agg'],
      ['dim_customers', 'dim_tx_x_account'],
      ['dim_account_tx_agg', 'dim_tx_x_account'],
      ['dim_customers', 'fct_c360_profile'],
      ['dim_tx_x_account', 'fct_c360_profile'],
      ['src_transactions', 'fct_merchant_streak'],
    ].map(([source, target]) => ({ source, target }))

    const result = layoutGraph(nodes, edges)
    expect(result).toHaveLength(nodes.length) // sink node is not leaked
    const pos = Object.fromEntries(result.map((r) => [r.id, r.position]))

    const maxX = Math.max(...result.map((r) => r.position.x))
    expect(pos.fct_merchant_streak.x).toBe(maxX)
    expect(pos.fct_c360_profile.x).toBe(maxX)
    expect(pos.fct_merchant_streak.y).not.toBe(pos.fct_c360_profile.y)

    // No two nodes in the same column are closer than a node height.
    for (const a of result) {
      for (const b of result) {
        if (a.id < b.id && a.position.x === b.position.x) {
          expect(Math.abs(a.position.y - b.position.y)).toBeGreaterThanOrEqual(60)
        }
      }
    }
  })
})
