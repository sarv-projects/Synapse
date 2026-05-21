import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Send, Loader2, CheckCircle, XCircle,
  Star, ExternalLink, Code2, ChevronDown, ChevronUp,
  Lightbulb, Clock, Hash
} from 'lucide-react'
import { Reveal } from '@/components/Reveal'

interface QueryResult {
  success: boolean
  natural_query: string
  cypher_query: string
  results: any[]
  result_count: number
  execution_time: number
  error?: string
}

// ── Detect entity type from result keys ──────────────────────────────────────
function detectType(item: Record<string, any>): 'tool' | 'model' | 'paper' | 'generic' {
  const keys = Object.keys(item).join(' ')
  if (keys.includes('full_name') || keys.includes('stargazers')) return 'tool'
  if (keys.includes('pipeline_tag') || keys.includes('downloads') || keys.includes('likes')) return 'model'
  if (keys.includes('arxiv_id') || keys.includes('title') || keys.includes('summary')) return 'paper'
  return 'generic'
}

// ── Flatten nested result (t.full_name → full_name) ──────────────────────────
function flattenResult(item: Record<string, any>): Record<string, any> {
  const flat: Record<string, any> = {}
  for (const [k, v] of Object.entries(item)) {
    const cleanKey = k.includes('.') ? k.split('.').slice(1).join('.') : k
    if (v !== null && v !== undefined && v !== '') flat[cleanKey] = v
  }
  return flat
}

// ── Tool result card ──────────────────────────────────────────────────────────
function ToolCard({ item }: { item: Record<string, any> }) {
  const d = item  // already flattened by ResultCard
  const name = d.full_name || d.name || 'Unknown'
  const desc = d.description || ''
  const stars = d.stargazers_count
  const lang = d.language
  const url = d.html_url || (name.includes('/') ? `https://github.com/${name}` : null)

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 hover:shadow-md
                    hover:-translate-y-0.5 transition-all duration-200">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-gray-900 text-sm">{name}</span>
            {lang && (
              <span className="px-2 py-0.5 rounded-full text-xs bg-indigo-50 text-indigo-700 border border-indigo-100">
                {lang}
              </span>
            )}
          </div>
          {desc && (
            <p className="text-xs text-gray-500 mt-1 line-clamp-2 leading-relaxed">{desc}</p>
          )}
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {stars != null && (
            <div className="flex items-center gap-1 text-xs font-medium text-gray-600">
              <Star className="w-3.5 h-3.5 text-indigo-400" />
              {Number(stars).toLocaleString()}
            </div>
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

// ── Model result card ─────────────────────────────────────────────────────────
function ModelCard({ item }: { item: Record<string, any> }) {
  const d = item  // already flattened by ResultCard
  const name = d.id || d.modelId || d.name || 'Unknown'
  const tag = d.pipeline_tag
  const likes = d.likes
  const downloads = d.downloads
  const url = name.includes('/') ? `https://huggingface.co/${name}` : null

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 hover:shadow-md
                    hover:-translate-y-0.5 transition-all duration-200">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-gray-900 text-sm truncate">{name}</span>
            {tag && (
              <span className="px-2 py-0.5 rounded-full text-xs bg-violet-50 text-violet-700 border border-violet-100">
                {tag}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0 text-xs text-gray-500">
          {likes != null && (
            <span className="flex items-center gap-1">
              <span className="text-rose-400">♥</span> {Number(likes).toLocaleString()}
            </span>
          )}
          {downloads != null && (
            <span className="flex items-center gap-1">
              ↓ {Number(downloads).toLocaleString()}
            </span>
          )}
          {url && (
            <a href={url} target="_blank" rel="noopener noreferrer"
              className="p-1.5 rounded-lg text-gray-400 hover:text-violet-600 hover:bg-violet-50 transition-colors">
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Paper result card ─────────────────────────────────────────────────────────
function PaperCard({ item }: { item: Record<string, any> }) {
  const d = item  // already flattened by ResultCard
  const title = d.title || 'Untitled'
  const summary = d.summary || ''
  const arxivId = d.arxiv_id
  const link = d.link || (arxivId ? `https://arxiv.org/abs/${arxivId}` : null)

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 hover:shadow-md
                    hover:-translate-y-0.5 transition-all duration-200">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-gray-900 text-sm leading-snug">{title}</p>
          {summary && (
            <p className="text-xs text-gray-500 mt-1 line-clamp-2 leading-relaxed">{summary}</p>
          )}
          {arxivId && (
            <span className="inline-flex items-center gap-1 mt-1.5 text-xs text-gray-400">
              <Hash className="w-3 h-3" /> {arxivId}
            </span>
          )}
        </div>
        {link && (
          <a href={link} target="_blank" rel="noopener noreferrer"
            className="p-1.5 rounded-lg text-gray-400 hover:text-emerald-600 hover:bg-emerald-50 transition-colors shrink-0">
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}
      </div>
    </div>
  )
}

// ── Generic fallback card ─────────────────────────────────────────────────────
function GenericCard({ item }: { item: Record<string, any> }) {
  const d = item  // already flattened by ResultCard
  const SKIP = ['created_at', 'last_seen', 'status', 'confidence', 'source', '_id', 'node_id',
                'commits_url', 'pulls_url', 'hooks_url', 'trees_url', 'git_url', 'ssh_url',
                'clone_url', 'svn_url', 'archive_url', 'downloads_url', 'issues_url',
                'events_url', 'labels_url', 'releases_url', 'deployments_url', 'git_refs_url',
                'git_commits_url', 'compare_url', 'merges_url', 'blobs_url', 'tags_url',
                'teams_url', 'keys_url', 'assignees_url', 'branches_url', 'collaborators_url',
                'comments_url', 'issue_comment_url', 'contents_url', 'subscribers_url',
                'subscription_url', 'notifications_url', 'milestones_url', 'statuses_url',
                'stargazers_url', 'forks_url', 'watchers_count', 'open_issues_count',
                'has_issues', 'has_projects', 'has_downloads', 'has_wiki', 'has_pages',
                'has_discussions', 'fork', 'archived', 'disabled', 'private', 'is_template',
                'web_commit_signoff_required', 'allow_forking', 'visibility', 'default_branch',
                'permissions', 'owner', 'license', 'topics', 'pull_request_creation_policy']

  const entries = Object.entries(d)
    .filter(([k]) => !SKIP.includes(k))
    .slice(0, 6)

  const name = d.full_name || d.name || d.title || d.id || 'Result'

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
      <p className="font-semibold text-gray-900 text-sm mb-2">{String(name)}</p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        {entries.map(([k, v]) => (
          <div key={k} className="flex gap-1.5 text-xs">
            <span className="text-gray-400 capitalize shrink-0">{k.replace(/_/g, ' ')}:</span>
            <span className="text-gray-700 truncate">{String(v).slice(0, 60)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Result card dispatcher ────────────────────────────────────────────────────
function ResultCard({ item, index }: { item: Record<string, any>; index: number }) {
  const flat = flattenResult(item)   // flatten first
  const type = detectType(flat)      // then detect on clean keys
  return (
    <Reveal direction="up" delay={Math.min(index * 30, 300)}>
      {type === 'tool'    ? <ToolCard item={flat} /> :
       type === 'model'   ? <ModelCard item={flat} /> :
       type === 'paper'   ? <PaperCard item={flat} /> :
                            <GenericCard item={flat} />}
    </Reveal>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export function Ask() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<QueryResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [showCypher, setShowCypher] = useState(false)

  const { data: suggestions } = useQuery({
    queryKey: ['query-suggestions'],
    queryFn: () => fetch('/api/v1/query/suggestions').then(r => r.json()),
  })

  const EXAMPLE_QUERIES = [
    'Show me the most starred AI tools',
    'Find models for text generation',
    'Which tools have over 10,000 stars?',
    'Show me the top 5 most downloaded models',
    'Find Python tools for computer vision',
  ]

  const executeQuery = async (q?: string) => {
    const text = q || query
    if (!text.trim()) return
    setLoading(true)
    setResult(null)
    setShowCypher(false)
    try {
      const res = await fetch('/api/v1/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ natural_query: text, max_results: 50 })
      })
      setResult(await res.json())
    } catch (e) {
      setResult({ success: false, error: String(e), natural_query: text, cypher_query: '', results: [], result_count: 0, execution_time: 0 })
    } finally {
      setLoading(false)
    }
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) executeQuery()
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <Reveal direction="up">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Ask SYNAPSE</h1>
          <p className="text-gray-500 text-sm mt-1">
            Ask anything about the AI knowledge graph in plain English.
          </p>
        </div>
      </Reveal>

      {/* ── Input ───────────────────────────────────────────────────────── */}
      <Reveal direction="up" delay={60}>
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-4">
          <textarea
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKey}
            placeholder="e.g. Show me the most starred AI tools, or find models for speech recognition..."
            className="w-full text-sm text-gray-900 placeholder-gray-400 resize-none outline-none
                       leading-relaxed min-h-[80px]"
            rows={3}
          />
          <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100">
            <span className="text-xs text-gray-400">Ctrl+Enter to submit</span>
            <button
              onClick={() => executeQuery()}
              disabled={!query.trim() || loading}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700
                         text-white text-sm font-semibold rounded-xl transition-colors
                         disabled:opacity-40 disabled:cursor-not-allowed shadow-sm shadow-indigo-200">
              {loading
                ? <><Loader2 className="w-4 h-4 animate-spin" /> Thinking…</>
                : <><Send className="w-4 h-4" /> Ask</>}
            </button>
          </div>
        </div>
      </Reveal>

      {/* ── Example queries ──────────────────────────────────────────────── */}
      {!result && !loading && (
        <Reveal direction="up" delay={120}>
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
              <Lightbulb className="w-3.5 h-3.5" /> Try these
            </p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLE_QUERIES.map(q => (
                <button key={q} onClick={() => { setQuery(q); executeQuery(q) }}
                  className="px-3 py-1.5 text-xs font-medium text-indigo-700 bg-indigo-50
                             border border-indigo-100 rounded-full hover:bg-indigo-100
                             transition-colors">
                  {q}
                </button>
              ))}
            </div>
          </div>
        </Reveal>
      )}

      {/* ── Loading skeleton ─────────────────────────────────────────────── */}
      {loading && (
        <div className="space-y-3">
          {[1,2,3].map(i => (
            <div key={i} className="bg-white rounded-xl border border-gray-100 p-4 animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-1/3 mb-2" />
              <div className="h-3 bg-gray-100 rounded w-2/3" />
            </div>
          ))}
        </div>
      )}

      {/* ── Results ──────────────────────────────────────────────────────── */}
      {result && !loading && (
        <div className="space-y-4">

          {/* Status bar */}
          <Reveal direction="up">
            <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border text-sm ${
              result.success
                ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                : 'bg-red-50 border-red-200 text-red-800'
            }`}>
              {result.success
                ? <CheckCircle className="w-4 h-4 shrink-0" />
                : <XCircle className="w-4 h-4 shrink-0" />}
              <span className="font-medium">
                {result.success
                  ? `${result.result_count} result${result.result_count !== 1 ? 's' : ''} found`
                  : result.error}
              </span>
              {result.success && result.execution_time > 0 && (
                <span className="ml-auto flex items-center gap-1 text-xs text-emerald-600">
                  <Clock className="w-3 h-3" />
                  {result.execution_time < 1 ? `${Math.round(result.execution_time * 1000)}ms` : `${result.execution_time.toFixed(2)}s`}
                </span>
              )}
            </div>
          </Reveal>

          {/* Cypher toggle */}
          {result.cypher_query && (
            <Reveal direction="up" delay={40}>
              <button onClick={() => setShowCypher(s => !s)}
                className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-700 transition-colors">
                <Code2 className="w-3.5 h-3.5" />
                {showCypher ? 'Hide' : 'Show'} generated Cypher
                {showCypher ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
              {showCypher && (
                <pre className="mt-2 p-3 bg-gray-950 text-emerald-400 text-xs rounded-xl
                                overflow-x-auto leading-relaxed font-mono">
                  {result.cypher_query}
                </pre>
              )}
            </Reveal>
          )}

          {/* Result cards */}
          {result.success && result.results.length > 0 && (
            <div className="space-y-2">
              {result.results.map((item, i) => (
                <ResultCard key={i} item={item} index={i} />
              ))}
            </div>
          )}

          {/* Empty state */}
          {result.success && result.results.length === 0 && (
            <Reveal direction="up" delay={60}>
              <div className="text-center py-12 bg-white rounded-2xl border border-gray-100">
                <p className="text-gray-400 text-sm">No results found.</p>
                <p className="text-gray-400 text-xs mt-1">Try rephrasing — e.g. "most starred tools" instead of "latest tools today"</p>
              </div>
            </Reveal>
          )}
        </div>
      )}
    </div>
  )
}
