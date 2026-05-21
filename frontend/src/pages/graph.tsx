import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Network, ZoomIn, ZoomOut, Download, Search, Maximize2, Minimize2 } from 'lucide-react'

// Sigma / Graphology are loaded lazily to avoid SSR issues
// and because they're large WebGL bundles.
// We render a canvas-based placeholder until the graph data arrives.

const NODE_COLORS: Record<string, string> = {
  Paper: '#6366f1',
  Model: '#14b8a6',
  Tool: '#f59e0b',
  Technique: '#1e3a8a',
  Author: '#6b7280',
  Organization: '#065f46',
}

interface RawNode { id: string; label: string; x?: number; y?: number; size?: number; properties: Record<string, any> }
interface RawEdge { id: string; source: string; target: string; type: string }

export function GraphExplorer() {
  const { entity } = useParams<{ entity: string }>()
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedNode, setSelectedNode] = useState<RawNode | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const sigmaRef = useRef<any>(null)

  const { data: graphData, isLoading, error } = useQuery({
    queryKey: ['graph-data', entity],
    queryFn: async () => {
      const res = await fetch(`/api/v1/technique/${entity}/ecosystem`)
      if (!res.ok) throw new Error('Failed to fetch graph data')
      return res.json()
    },
    enabled: !!entity,
  })

  // Dynamically import Sigma + Graphology only when data is ready
  useEffect(() => {
    if (!graphData || !containerRef.current) return

    let cancelled = false

    ;(async () => {
      const [{ default: Graph }, { Sigma }] = await Promise.all([
        import('graphology'),
        import('sigma'),
      ])

      if (cancelled || !containerRef.current) return

      const graph = new Graph()

      ;(graphData.nodes as RawNode[]).forEach(n => {
        graph.addNode(n.id, {
          label: n.label,
          x: n.x ?? Math.random(),
          y: n.y ?? Math.random(),
          size: n.size ?? 8,
          color: NODE_COLORS[n.label] ?? '#6b7280',
          ...n.properties,
        })
      })

      ;(graphData.edges as RawEdge[]).forEach(e => {
        if (!graph.hasEdge(e.source, e.target)) {
          graph.addEdge(e.source, e.target, { label: e.type })
        }
      })

      if (sigmaRef.current) sigmaRef.current.kill()
      sigmaRef.current = new Sigma(graph, containerRef.current!)

      sigmaRef.current.on('clickNode', ({ node }: { node: string }) => {
        const attrs = graph.getNodeAttributes(node)
        setSelectedNode({ id: node, label: attrs.label, properties: attrs })
      })
    })()

    return () => { cancelled = true }
  }, [graphData])

  useEffect(() => () => { sigmaRef.current?.kill() }, [])

  const handleExport = useCallback(() => {
    if (!graphData) return
    const blob = new Blob([JSON.stringify(graphData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `synapse-graph-${entity}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, [graphData, entity])

  if (!entity) return (
    <div className="flex items-center justify-center min-h-screen text-gray-500">
      <div className="text-center"><Network className="w-10 h-10 mx-auto mb-3" /><p>No entity selected.</p></div>
    </div>
  )

  if (isLoading) return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600" />
    </div>
  )

  if (error) return (
    <div className="flex items-center justify-center min-h-screen text-red-600">
      <div className="text-center"><Network className="w-8 h-8 mx-auto mb-2" /><p>Failed to load graph.</p></div>
    </div>
  )

  return (
    <div className="h-screen flex flex-col">
      {/* Toolbar */}
      <div className="bg-white dark:bg-gray-800 shadow-sm border-b border-gray-200 dark:border-gray-700 p-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-gray-900 dark:text-white">Graph: {entity}</h1>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 w-4 h-4" />
            <input value={searchTerm} onChange={e => setSearchTerm(e.target.value)}
              placeholder="Search nodes…"
              className="pl-8 pr-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm dark:bg-gray-700 dark:text-white" />
          </div>
        </div>
        <button onClick={handleExport} title="Export JSON"
          className="p-2 text-gray-600 dark:text-gray-400 hover:text-indigo-600 transition-colors">
          <Download className="w-4 h-4" />
        </button>
      </div>

      {/* Graph canvas */}
      <div className="flex-1 relative bg-gray-50 dark:bg-gray-900">
        <div ref={containerRef} className="w-full h-full" />

        {/* Legend */}
        <div className="absolute bottom-4 left-4 bg-white dark:bg-gray-800 rounded-lg shadow p-3 text-xs space-y-1">
          {Object.entries(NODE_COLORS).map(([label, color]) => (
            <div key={label} className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full inline-block" style={{ background: color }} />
              <span className="text-gray-700 dark:text-gray-300">{label}</span>
            </div>
          ))}
        </div>

        {/* Node detail panel */}
        {selectedNode && (
          <div className="absolute top-4 right-4 w-72 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-gray-900 dark:text-white">Node Details</h3>
              <button onClick={() => setSelectedNode(null)} className="text-gray-400 hover:text-gray-600">
                <Minimize2 className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-2 text-sm">
              <div><span className="text-gray-500">Type: </span><span className="font-medium text-gray-900 dark:text-white">{selectedNode.label}</span></div>
              {Object.entries(selectedNode.properties)
                .filter(([k]) => !['embedding', 'x', 'y', 'size', 'color'].includes(k))
                .slice(0, 8)
                .map(([k, v]) => (
                  <div key={k}>
                    <span className="text-gray-500 capitalize">{k.replace(/_/g, ' ')}: </span>
                    <span className="text-gray-900 dark:text-gray-100">{String(v).slice(0, 80)}</span>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
