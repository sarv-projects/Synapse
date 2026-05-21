import React, { useState } from 'react'
import { Download, FileJson, FileText, Network } from 'lucide-react'

type Format = 'json-ld' | 'csv' | 'graphml'

export function Export() {
  const [query, setQuery] = useState('')
  const [format, setFormat] = useState<Format>('json-ld')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const formats: { key: Format; label: string; icon: React.ReactNode }[] = [
    { key: 'json-ld', label: 'JSON-LD', icon: <FileJson className="w-4 h-4" /> },
    { key: 'csv', label: 'CSV (ZIP)', icon: <FileText className="w-4 h-4" /> },
    { key: 'graphml', label: 'GraphML', icon: <Network className="w-4 h-4" /> },
  ]

  const handleExport = async () => {
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/v1/export?query=${encodeURIComponent(query)}&format=${format}`)
      if (!res.ok) throw new Error(await res.text())
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `synapse-export.${format === 'csv' ? 'zip' : format === 'json-ld' ? 'jsonld' : 'graphml'}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Download className="w-6 h-6" /> Export Subgraph
        </h1>
        <p className="text-gray-600 dark:text-gray-400 mt-1">Export up to 500 nodes as JSON-LD, CSV, or GraphML.</p>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Cypher Query</label>
          <textarea value={query} onChange={e => setQuery(e.target.value)} rows={4}
            placeholder="MATCH (n:Paper)-[r]->(m) WHERE n.year = 2025 RETURN n, r, m LIMIT 100"
            className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 dark:bg-gray-700 dark:text-white font-mono text-sm" />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Format</label>
          <div className="flex gap-2">
            {formats.map(f => (
              <button key={f.key} onClick={() => setFormat(f.key)}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  format === f.key
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                }`}>
                {f.icon}{f.label}
              </button>
            ))}
          </div>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button onClick={handleExport} disabled={!query.trim() || loading}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg disabled:opacity-50 transition-colors">
          <Download className="w-4 h-4" />
          {loading ? 'Exporting…' : 'Export'}
        </button>
      </div>
    </div>
  )
}
