import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Trophy, Star, TrendingUp } from 'lucide-react'

type Tab = 'tools' | 'papers' | 'techniques'

export function Leaderboard() {
  const [tab, setTab] = useState<Tab>('tools')

  const { data, isLoading } = useQuery({
    queryKey: ['leaderboard', tab],
    queryFn: async () => {
      const res = await fetch(`/api/v1/leaderboard?type=${tab}&limit=20`)
      if (!res.ok) throw new Error('Failed to fetch leaderboard')
      return res.json()
    },
  })

  const tabs: { key: Tab; label: string }[] = [
    { key: 'tools', label: 'Top Tools' },
    { key: 'papers', label: 'Top Papers' },
    { key: 'techniques', label: 'Top Techniques' },
  ]

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Trophy className="w-6 h-6 text-indigo-500" /> Leaderboards
        </h1>
      </div>

      <div className="flex gap-2">
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === t.key
                ? 'bg-indigo-600 text-white'
                : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {isLoading && <div className="text-center py-12 text-gray-500">Loading…</div>}

      {data && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow divide-y divide-gray-200 dark:divide-gray-700">
          {(data.items || []).map((item: any, i: number) => (
            <div key={i} className="p-4 flex items-center gap-4">
              <span className="text-lg font-bold text-gray-400 w-8 text-right">{i + 1}</span>
              <div className="flex-1">
                <p className="font-medium text-gray-900 dark:text-white">{item.name}</p>
                {item.description && <p className="text-sm text-gray-500 mt-0.5 line-clamp-1">{item.description}</p>}
              </div>
              {item.stars != null && (
                <span className="flex items-center gap-1 text-sm text-indigo-600">
                  <Star className="w-4 h-4" />{item.stars.toLocaleString()}
                </span>
              )}
              {item.score != null && (
                <span className="flex items-center gap-1 text-sm text-indigo-600">
                  <TrendingUp className="w-4 h-4" />{item.score}
                </span>
              )}
            </div>
          ))}
          {!data.items?.length && (
            <div className="p-8 text-center text-gray-500">No data yet.</div>
          )}
        </div>
      )}
    </div>
  )
}
