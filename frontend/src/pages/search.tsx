import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, ExternalLink, Star, ChevronDown, X, Loader2 } from 'lucide-react'
import { Reveal } from '@/components/Reveal'

interface SearchResult {
  id: string
  label: string
  name: string
  properties: Record<string, any>
  confidence?: number
  evidence_url?: string
  source: string
}

const ENTITY_TYPES = ['all', 'Tool', 'Model', 'Paper', 'Technique', 'Organization', 'Author']

const LABEL_COLORS: Record<string, string> = {
  Tool:         'bg-indigo-50 text-indigo-700 border-indigo-100',
  Model:        'bg-violet-50 text-violet-700 border-violet-100',
  Paper:        'bg-emerald-50 text-emerald-700 border-emerald-100',
  Technique:    'bg-sky-50 text-sky-700 border-sky-100',
  Organization: 'bg-orange-50 text-orange-700 border-orange-100',
  Author:       'bg-pink-50 text-pink-700 border-pink-100',
}

function ResultCard({ result }: { result: SearchResult }) {
  const p = result.properties
  const labelColor = LABEL_COLORS[result.label] || 'bg-gray-50 text-gray-700 border-gray-100'

  // Pick the best description field
  const description = p.description || p.summary || p.abstract_summary || ''
  const stars = p.stargazers_count
  const likes = p.likes
  const downloads = p.downloads
  const lang = p.language
  const tag = p.pipeline_tag
  const url = result.evidence_url || p.html_url || p.link || ''

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4
                    hover:shadow-md hover:-translate-y-0.5 transition-all duration-200">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {/* Name + label badge */}
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${labelColor}`}>
              {result.label}
            </span>
            <span className="font-semibold text-gray-900 text-sm truncate">{result.name}</span>
            {lang && (
              <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-600">
                {lang}
              </span>
            )}
            {tag && (
              <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-600">
                {tag}
              </span>
            )}
          </div>

          {/* Description */}
          {description && (
            <p className="text-xs text-gray-500 leading-relaxed line-clamp-2">{description}</p>
          )}
        </div>

        {/* Stats + link */}
        <div className="flex items-center gap-3 shrink-0 text-xs text-gray-500">
          {stars != null && (
            <span className="flex items-center gap-1">
              <Star className="w-3.5 h-3.5 text-indigo-400" />
              {Number(stars).toLocaleString()}
            </span>
          )}
          {likes != null && (
            <span className="flex items-center gap-1">
              <span className="text-rose-400">♥</span>
              {Number(likes).toLocaleString()}
            </span>
          )}
          {downloads != null && (
            <span>↓ {Number(downloads).toLocaleString()}</span>
          )}
          {url && (
            <a href={url} target="_blank" rel="noopener noreferrer"
              className="p-1.5 rounded-lg text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors">
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}
        </div>
      </div>
    </div>
  )
}

export function SearchPage() {
  const [query, setQuery] = useState('')
  const [submitted, setSubmitted] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')

  const { data, isLoading, error } = useQuery({
    queryKey: ['search', submitted, typeFilter],
    queryFn: async () => {
      const params = new URLSearchParams({ q: submitted, limit: '50' })
      if (typeFilter !== 'all') params.set('type', typeFilter)
      const res = await fetch(`/api/v1/search?${params}`)
      if (!res.ok) throw new Error('Search failed')
      return res.json()
    },
    enabled: submitted.length > 0,
  })

  const handleSearch = () => {
    if (query.trim()) setSubmitted(query.trim())
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSearch()
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">

      {/* Header */}
      <Reveal direction="up">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Search</h1>
          <p className="text-gray-500 text-sm mt-1">
            Search across tools, models, papers, techniques, and organizations.
          </p>
        </div>
      </Reveal>

      {/* Search bar */}
      <Reveal direction="up" delay={60}>
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-4 space-y-3">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 w-4 h-4" />
              <input
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={handleKey}
                placeholder="e.g. pytorch, text generation, huggingface..."
                className="w-full pl-9 pr-4 py-2.5 text-sm border border-gray-200 rounded-xl
                           focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent
                           text-gray-900 placeholder-gray-400"
              />
            </div>
            <button
              onClick={handleSearch}
              disabled={!query.trim() || isLoading}
              className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700
                         text-white text-sm font-semibold rounded-xl transition-colors
                         disabled:opacity-40 shadow-sm shadow-indigo-200">
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              Search
            </button>
          </div>

          {/* Type filter */}
          <div className="flex items-center gap-2 flex-wrap">
            {ENTITY_TYPES.map(t => (
              <button key={t} onClick={() => setTypeFilter(t)}
                className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                  typeFilter === t
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}>
                {t === 'all' ? 'All types' : t}
              </button>
            ))}
          </div>
        </div>
      </Reveal>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
          <X className="w-4 h-4 shrink-0" /> Search failed. Please try again.
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="space-y-2">
          {[1,2,3,4,5].map(i => (
            <div key={i} className="bg-white rounded-xl border border-gray-100 p-4 animate-pulse">
              <div className="flex gap-2 mb-2">
                <div className="h-5 w-16 bg-gray-200 rounded-full" />
                <div className="h-5 w-40 bg-gray-200 rounded" />
              </div>
              <div className="h-3 w-3/4 bg-gray-100 rounded" />
            </div>
          ))}
        </div>
      )}

      {/* Results */}
      {data && !isLoading && (
        <>
          {data.results.length > 0 && (
            <Reveal direction="fade">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                {data.results.length} result{data.results.length !== 1 ? 's' : ''}
                {typeFilter !== 'all' ? ` · ${typeFilter}` : ''}
              </p>
            </Reveal>
          )}

          <div className="space-y-2">
            {data.results.map((result: SearchResult, i: number) => (
              <Reveal key={result.id || i} direction="up" delay={Math.min(i * 25, 250)}>
                <ResultCard result={result} />
              </Reveal>
            ))}
          </div>

          {data.results.length === 0 && submitted && (
            <Reveal direction="up">
              <div className="text-center py-16 bg-white rounded-2xl border border-gray-100">
                <Search className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                <p className="text-gray-500 font-medium">No results for "{submitted}"</p>
                <p className="text-gray-400 text-sm mt-1">Try a different term or remove the type filter.</p>
              </div>
            </Reveal>
          )}
        </>
      )}

      {/* Empty state before search */}
      {!submitted && !isLoading && (
        <Reveal direction="up" delay={120}>
          <div className="text-center py-16 text-gray-400">
            <Search className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="text-sm">Type something above to search the knowledge graph.</p>
          </div>
        </Reveal>
      )}
    </div>
  )
}

export { SearchPage as Search }
