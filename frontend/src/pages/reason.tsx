import { useState, useEffect, useRef } from 'react'
import DOMPurify from 'dompurify'

interface ResultType {
  markdown?: string
  synthesis_markdown?: string
  sources?: { url: string; title: string; source: string; snippet: string }[]
  gaps?: string[]
  contradictions?: Record<string, unknown>[]
  model_trace?: Record<string, string>
  total_tokens?: Record<string, number>
  retrieval_confidence?: number
  web_research_used?: boolean
  ragas_eval?: {
    faithfulness: number
    answer_relevancy: number
    context_precision: number
    context_recall: number
  }
}

const STAGES = ['Budget Check', 'Decomposition', 'Retrieval', 'Web Research', 'Analysis', 'Synthesis', 'Critique']
const STAGE_MAP: Record<string, number> = {
  entry: 0, decomposition: 1, retrieval: 2, web_research: 3,
  analysis_crew: 4, synthesis: 5, critic: 6, output: 7
}

export default function Reason() {
  const [query, setQuery] = useState('')
  const [jobId, setJobId] = useState('')
  const [status, setStatus] = useState('')
  const [currentNode, setCurrentNode] = useState('')
  const [result, setResult] = useState<ResultType | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const eventSourceRef = useRef<EventSource | null>(null)

  const submitQuery = async () => {
    if (!query.trim()) return
    setLoading(true)
    setResult(null)
    setError('')
    setStatus('')
    setCurrentNode('')

    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    try {
      const res = await fetch('/api/v1/reason', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim() })
      })
      const data = await res.json()
      setJobId(data.job_id)
      setStatus(data.status)

      // Start SSE stream
      const eventSource = new EventSource(`/api/v1/reason/${data.job_id}/stream`)
      eventSourceRef.current = eventSource

      eventSource.onmessage = (event) => {
        const d = JSON.parse(event.data)
        if (d.error) {
          setError(d.error)
          setLoading(false)
          eventSource.close()
          return
        }

        setStatus(d.status)
        setCurrentNode(d.current_node || (d.status === 'COMPLETE' ? 'output' : ''))

        if (d.status === 'COMPLETE' || d.status === 'FAILED') {
          eventSource.close()
          setLoading(false)
          if (d.status === 'COMPLETE') setResult(d.result)
          else setError(d.error || 'Pipeline failed')
        }
      }

      eventSource.onerror = (err) => {
        console.error("SSE Error:", err)
        setError("Connection lost to reasoning stream.")
        setLoading(false)
        eventSource.close()
      }
    } catch (e) {
      setError(String(e))
      setLoading(false)
    }
  }

  useEffect(() => () => {
    if (eventSourceRef.current) eventSourceRef.current.close()
  }, [])

  const stageIndex = STAGE_MAP[currentNode] ?? -1

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">Deep Reasoning</h1>
        <p className="text-slate-400">Multi-agent analysis grounded in the SYNAPSE knowledge graph</p>
      </div>

      <div className="mb-6">
        <textarea
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && e.ctrlKey) submitQuery() }}
          placeholder="Ask an analytical question... e.g. How have the trade-offs of LoRA vs full fine-tuning evolved since 2022?"
          rows={4}
          className="w-full bg-slate-800 border border-slate-700 rounded-lg p-4 text-white placeholder-slate-500 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500"
          disabled={loading}
        />
        <button
          onClick={submitQuery}
          disabled={loading || !query.trim()}
          className="mt-3 px-6 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg transition-colors"
        >
          {loading ? 'Analyzing...' : 'Submit Query'}
        </button>
      </div>

      {loading && (
        <div className="mb-6">
          <div className="flex flex-wrap gap-2">
            {STAGES.map((stage, i) => (
              <div key={stage} className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                i < stageIndex ? 'bg-emerald-600 text-white' :
                i === stageIndex ? 'bg-indigo-600 text-white animate-pulse' :
                'bg-slate-800 text-slate-500'
              }`}>
                {stage}
              </div>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-900/30 border border-red-800 rounded-lg p-4 text-red-300 mb-6">{error}</div>
      )}

      {status === 'COMPLETE' && result && (
        <div className="space-y-6">
          <div className="flex gap-3 text-xs text-slate-400 flex-wrap">
            {result.retrieval_confidence !== undefined && <span>Confidence: {(result.retrieval_confidence * 100).toFixed(0)}%</span>}
            {result.web_research_used && <span className="text-amber-400">Web research used</span>}
            {result.model_trace && <span>Models: {Object.values(result.model_trace).join(', ')}</span>}
          </div>

          {result.ragas_eval && (
            <div className="flex gap-4 flex-wrap text-xs">
              <span className="px-2 py-1 bg-slate-800 rounded">
                Faithfulness: <strong className={result.ragas_eval.faithfulness >= 0.8 ? 'text-emerald-400' : result.ragas_eval.faithfulness >= 0.5 ? 'text-amber-400' : 'text-red-400'}>{(result.ragas_eval.faithfulness * 100).toFixed(0)}%</strong>
              </span>
              <span className="px-2 py-1 bg-slate-800 rounded">
                Relevancy: <strong className={result.ragas_eval.answer_relevancy >= 0.8 ? 'text-emerald-400' : result.ragas_eval.answer_relevancy >= 0.5 ? 'text-amber-400' : 'text-red-400'}>{(result.ragas_eval.answer_relevancy * 100).toFixed(0)}%</strong>
              </span>
              <span className="px-2 py-1 bg-slate-800 rounded">
                Precision: <strong className={result.ragas_eval.context_precision >= 0.8 ? 'text-emerald-400' : result.ragas_eval.context_precision >= 0.5 ? 'text-amber-400' : 'text-red-400'}>{(result.ragas_eval.context_precision * 100).toFixed(0)}%</strong>
              </span>
              <span className="px-2 py-1 bg-slate-800 rounded">
                Recall: <strong className={result.ragas_eval.context_recall >= 0.8 ? 'text-emerald-400' : result.ragas_eval.context_recall >= 0.5 ? 'text-amber-400' : 'text-red-400'}>{(result.ragas_eval.context_recall * 100).toFixed(0)}%</strong>
              </span>
            </div>
          )}

          <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 overflow-x-auto">
            <div className="prose prose-invert max-w-none text-sm" dangerouslySetInnerHTML={{ __html: renderMarkdown(result.synthesis_markdown || result.markdown || '') }} />
          </div>

          {result.sources && result.sources.length > 0 && (
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-3">Sources</h3>
              <div className="space-y-2 text-sm">
                {result.sources.map((s, i) => (
                  <div key={i} className="text-slate-400">
                    <span className="text-slate-500">[{i + 1}]</span>{' '}
                    {s.url ? <a href={s.url} target="_blank" rel="noopener" className="text-indigo-400 hover:underline">{s.title || s.url}</a> : s.title}
                    {s.source && <span className="ml-2 text-xs bg-slate-700 px-1.5 py-0.5 rounded">{s.source}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {result.gaps && result.gaps.length > 0 && (
            <div className="bg-amber-900/20 border border-amber-800 rounded-lg p-4 text-amber-300 text-sm">
              <strong>Knowledge Gaps:</strong> {result.gaps.join(', ')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function renderMarkdown(md: string): string {
  if (!md) return ''
  let html = md
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-slate-900 p-3 rounded text-xs overflow-x-auto"><code>$2</code></pre>')
    .replace(/`([^`]+)`/g, '<code class="bg-slate-700 px-1 rounded text-xs">$1</code>')
    .replace(/^### (.+)$/gm, '<h3 class="text-lg font-semibold mt-4 mb-1">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-xl font-semibold mt-5 mb-2">$1</h2>')
    .replace(/^- (.+)$/gm, '<li class="ml-4">- $1</li>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/\n\n/g, '<br/><br/>')
  // Simple pipe table rendering
  html = html.replace(/\|(.+)\|\n\|[-| ]+\|\n((?:\|.+\|\n?)*)/g, (_, header, rows) => {
    const hcols = header.split('|').filter((c: string) => c.trim()).map((c: string) => `<th class="border border-slate-600 px-2 py-1 text-left">${c.trim()}</th>`).join('')
    const rrows = rows.trim().split('\n').map((row: string) => {
      const cols = row.split('|').filter((c: string) => c.trim()).map((c: string) => `<td class="border border-slate-600 px-2 py-1">${c.trim()}</td>`).join('')
      return `<tr>${cols}</tr>`
    }).join('')
    return `<table class="border-collapse border border-slate-600 my-2 text-sm"><thead><tr>${hcols}</tr></thead><tbody>${rrows}</tbody></table>`
  })
  return DOMPurify.sanitize(html, { ALLOWED_TAGS: ['h2', 'h3', 'p', 'br', 'strong', 'em', 'code', 'pre', 'li', 'ul', 'ol', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'a', 'span'], ALLOWED_ATTR: ['class', 'href', 'target', 'rel'] })
}
