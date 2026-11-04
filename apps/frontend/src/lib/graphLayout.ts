import dagre from '@dagrejs/dagre'
import type { GraphEdge, GraphNode } from '../types/dataProduct'

// Wide enough for the longest label plus the PRODUCT badge, so neighbouring
// ranks never overlap and edges are not hidden behind a node.
const NODE_WIDTH = 260
const NODE_HEIGHT = 60
const PRODUCT_SINK = '__product_sink__'
const PRODUCT_EDGE_WEIGHT = 100

export interface LayoutPosition {
  id: string
  position: { x: number; y: number }
}

/**
 * Assigns left-to-right coordinates to graph nodes using dagre's layered
 * layout algorithm. Pure function: no React/DOM dependency.
 *
 * Data-product nodes (``is_product``) are pulled into the right-most column,
 * even when they have no downstream statement, via a throw-away sink node that
 * every product feeds with a heavy edge.
 */
export function layoutGraph(nodes: GraphNode[], edges: GraphEdge[]): LayoutPosition[] {
  const graph = new dagre.graphlib.Graph()
  graph.setDefaultEdgeLabel(() => ({}))
  graph.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 80 })

  for (const node of nodes) {
    graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  }

  for (const edge of edges) {
    graph.setEdge(edge.source, edge.target)
  }

  const products = nodes.filter((n) => n.is_product)
  if (products.length > 0) {
    graph.setNode(PRODUCT_SINK, { width: 1, height: 1 })
    for (const node of products) {
      graph.setEdge(node.id, PRODUCT_SINK, { weight: PRODUCT_EDGE_WEIGHT })
    }
  }

  dagre.layout(graph)

  return nodes.map((node) => {
    const { x, y } = graph.node(node.id)
    return { id: node.id, position: { x, y } }
  })
}
