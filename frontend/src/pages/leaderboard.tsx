import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Trophy, Star, TrendingUp } from 'lucide-react'

type Tab = 'tools' | 'papers' | 'techniques' | 'models'

export function Leaderboard() {
  const [tab, setTab] = useState<Tab>('tools')
  const [subCategory, setSubCategory] = useState<string>('overall')

  const { data, isLoading } = useQuery({
    queryKey: ['leaderboard', tab, subCategory],
    queryFn: async () => {
      const url = tab === 'models'
        ? `/api/v1/leaderboard?type=${tab}&category=${subCategory}&limit=50`
        : `/api/v1/leaderboard?type=${tab}&limit=20`
      const res = await fetch(url)
      if (!res.ok) throw new Error('Failed to fetch leaderboard')
      return res.json()
    },
  })

  const tabs: { key: Tab; label: string }[] = [
    { key: 'tools', label: 'Top Tools' },
    { key: 'papers', label: 'Top Papers' },
    { key: 'techniques', label: 'Top Techniques' },
    { key: 'models', label: 'Top Models (LMArena)' },
  ]

  const subCategories = [
    { key: 'overall', label: '🌟 Overall' },
    { key: 'coding', label: '💻 Coding' },
    { key: 'math', label: '🔢 Math' },
    { key: 'instruction_following', label: '🧠 Instruction Following' },
    { key: 'creative_writing', label: '✍️ Creative Writing' },
    { key: 'hard_prompts', label: '🔥 Hard Prompts' },
  ]

  const handleTabChange = (t: Tab) => {
    setTab(t)
    setSubCategory('overall')
  }

  const getOrgColor = (org: string) => {
    const o = org.toLowerCase()
    if (o.includes('openai') || o.includes('gpt')) return 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-400 dark:border-emerald-800/50'
    if (o.includes('anthropic') || o.includes('claude')) return 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-400 dark:border-amber-800/50'
    if (o.includes('google') || o.includes('gemini') || o.includes('gemma')) return 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/30 dark:text-blue-400 dark:border-blue-800/50'
    if (o.includes('meta') || o.includes('llama') || o.includes('muse')) return 'bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-950/30 dark:text-indigo-400 dark:border-indigo-800/50'
    if (o.includes('alibaba') || o.includes('qwen')) return 'bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-950/30 dark:text-orange-400 dark:border-orange-800/50'
    if (o.includes('deepseek')) return 'bg-cyan-50 text-cyan-700 border-cyan-200 dark:bg-cyan-950/30 dark:text-cyan-400 dark:border-cyan-800/50'
    return 'bg-gray-50 text-gray-700 border-gray-200 dark:bg-gray-900/30 dark:text-gray-400 dark:border-gray-800/50'
  }

  const getLicenseColor = (lic: string) => {
    if (lic === 'Open Weights') return 'bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-950/30 dark:text-teal-400 dark:border-teal-800/50'
    return 'bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950/30 dark:text-purple-400 dark:border-purple-800/50'
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow p-6 border border-gray-150 dark:border-gray-700">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Trophy className="w-6 h-6 text-indigo-500" /> Leaderboards
        </h1>
        <p className="text-sm text-gray-500 mt-1 dark:text-gray-400">
          Rankings of the top tools, papers, techniques, and models across the artificial intelligence ecosystem.
        </p>
      </div>

      <div className="flex gap-2 flex-wrap">
        {tabs.map(t => (
          <button key={t.key} onClick={() => handleTabChange(t.key)}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-all duration-200 shadow-sm border ${
              tab === t.key
                ? 'bg-indigo-600 border-indigo-500 text-white shadow-indigo-500/10'
                : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'models' && (
        <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-none select-none">
          {subCategories.map(sub => (
            <button
              key={sub.key}
              onClick={() => setSubCategory(sub.key)}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-all duration-200 border ${
                subCategory === sub.key
                  ? 'bg-gradient-to-r from-violet-600 to-indigo-600 border-indigo-500 text-white shadow-md shadow-indigo-500/20 scale-102'
                  : 'bg-white hover:bg-gray-50 border-gray-200 text-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700 dark:border-gray-700 dark:text-gray-300'
              }`}
            >
              {sub.label}
            </button>
          ))}
        </div>
      )}

      {isLoading && <div className="text-center py-12 text-gray-500">Loading…</div>}

      {data && (
        <div className={
          tab === 'models'
            ? "grid grid-cols-1 md:grid-cols-2 gap-4"
            : "bg-white dark:bg-gray-800 rounded-2xl shadow border border-gray-200 dark:border-gray-700 divide-y divide-gray-250 dark:divide-gray-700"
        }>
          {(data.items || []).map((item: any, i: number) => {
            if (tab === 'models') {
              const parts = item.description ? item.description.split(' | ') : []
              const orgPart = parts.find((p: string) => p.startsWith('Org:')) || ''
              const org = orgPart ? orgPart.replace('Org: ', '') : 'Unknown'
              const datePart = parts.find((p: string) => p.startsWith('Date:')) || ''
              const date = datePart ? datePart.replace('Date: ', '') : ''

              return (
                <div key={i} className="group relative bg-white dark:bg-gray-800 rounded-xl p-5 border border-gray-200 dark:border-gray-700 hover:border-indigo-500/50 dark:hover:border-indigo-500/50 shadow-sm hover:shadow-md transition-all duration-300 flex flex-col justify-between overflow-hidden">
                  <div className="absolute inset-0 bg-gradient-to-tr from-indigo-500/0 via-indigo-500/0 to-indigo-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
                  
                  <div className="space-y-3 z-10">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <span className={`flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${
                          i === 0 ? 'bg-amber-100 text-amber-800' :
                          i === 1 ? 'bg-slate-100 text-slate-800' :
                          i === 2 ? 'bg-orange-100 text-orange-800' : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                        }`}>
                          {i + 1}
                        </span>
                        <h3 className="font-bold text-gray-900 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors line-clamp-1">{item.id}</h3>
                      </div>
                      
                      <div className="flex items-center gap-1.5 text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950/50 px-2.5 py-1 rounded-lg text-xs font-bold shadow-sm border border-indigo-100/50 dark:border-indigo-900/30">
                        <TrendingUp className="w-3.5 h-3.5" />
                        <span>{item.score.toLocaleString()}</span>
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-2 pt-1">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${getOrgColor(org)}`}>
                        {org}
                      </span>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${getLicenseColor(item.library)}`}>
                        {item.library}
                      </span>
                    </div>

                    <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed pt-1 line-clamp-2">
                      {item.description ? item.description.split(' | ')[0] : 'No description available'}
                    </p>
                  </div>

                  <div className="flex items-center justify-between border-t border-gray-100 dark:border-gray-700/50 mt-4 pt-3 text-[10px] text-gray-400 dark:text-gray-500 z-10">
                    <span>Rank #{i + 1} Overall</span>
                    {date && <span>Updated {date}</span>}
                  </div>
                </div>
              )
            }

            return (
              <div key={i} className="p-4 flex items-center gap-4 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors first:rounded-t-2xl last:rounded-b-2xl">
                <span className="text-lg font-bold text-gray-400 w-8 text-right">{i + 1}</span>
                <div className="flex-1">
                  <p className="font-medium text-gray-900 dark:text-white">{item.name}</p>
                  {item.description && <p className="text-sm text-gray-500 mt-0.5 line-clamp-1">{item.description}</p>}
                </div>
                {item.stars != null && (
                  <span className="flex items-center gap-1 text-sm text-indigo-600 dark:text-indigo-400">
                    <Star className="w-4 h-4" />{item.stars.toLocaleString()}
                  </span>
                )}
                {item.score != null && (
                  <span className="flex items-center gap-1 text-sm text-indigo-600 dark:text-indigo-400">
                    <TrendingUp className="w-4 h-4" />{item.score.toLocaleString()}
                  </span>
                )}
              </div>
            )
          })}
          {!data.items?.length && (
            <div className="p-8 text-center text-gray-500 col-span-full">No data yet.</div>
          )}
        </div>
      )}
    </div>
  )
}
