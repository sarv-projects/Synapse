import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { GitCompare, Plus, Minus, Calendar } from 'lucide-react'

export function Diff() {
  const [fromDate, setFromDate] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() - 7)
    return d.toISOString().split('T')[0]
  })
  const [toDate, setToDate] = useState(() => new Date().toISOString().split('T')[0])

  const { data, isLoading } = useQuery({
    queryKey: ['diff', fromDate, toDate],
    queryFn: async () => {
      const res = await fetch(`/api/v1/diff?from=${fromDate}&to=${toDate}`)
      if (!res.ok) throw new Error('Failed to fetch diff')
      return res.json()
    },
    enabled: !!fromDate && !!toDate,
  })

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
          <GitCompare className="w-6 h-6" /> What Changed
        </h1>
        <p className="text-gray-600 dark:text-gray-400">Compare the knowledge graph between two dates.</p>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 flex gap-4 flex-wrap">
        <div className="flex-1 min-w-[160px]">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">From</label>
          <input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)}
            className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 dark:bg-gray-700 dark:text-white" />
        </div>
        <div className="flex-1 min-w-[160px]">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">To</label>
          <input type="date" value={toDate} onChange={e => setToDate(e.target.value)}
            className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 dark:bg-gray-700 dark:text-white" />
        </div>
      </div>

      {isLoading && <div className="text-center py-12 text-gray-500">Loading diff…</div>}

      {data && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow divide-y divide-gray-200 dark:divide-gray-700">
          {(data.added || []).map((item: any, i: number) => (
            <div key={i} className="p-4 flex items-start gap-3">
              <Plus className="w-4 h-4 text-green-500 mt-0.5 shrink-0" />
              <div>
                <span className="font-medium text-gray-900 dark:text-white">{item.name}</span>
                <span className="ml-2 text-xs text-gray-500">{item.label}</span>
              </div>
            </div>
          ))}
          {(data.removed || []).map((item: any, i: number) => (
            <div key={i} className="p-4 flex items-start gap-3">
              <Minus className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
              <div>
                <span className="font-medium text-gray-900 dark:text-white">{item.name}</span>
                <span className="ml-2 text-xs text-gray-500">{item.label}</span>
              </div>
            </div>
          ))}
          {!data.added?.length && !data.removed?.length && (
            <div className="p-8 text-center text-gray-500">No changes in this period.</div>
          )}
        </div>
      )}
    </div>
  )
}
