import { useState, useEffect, useRef } from 'react'
import DOMPurify from 'dompurify'
import { motion, AnimatePresence } from 'motion/react'
import { Zap, BrainCircuit, Globe, Search, Activity, Target, Network, CheckCircle2, AlertTriangle, FileText, Database } from 'lucide-react'

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

const STAGES = [
  { id: 'entry', label: 'Budget Check', icon: Zap },
  { id: 'decomposition', label: 'Decomposition', icon: BrainCircuit },
  { id: 'retrieval', label: 'Retrieval', icon: Database },
  { id: 'web_research', label: 'Web Research', icon: Globe },
  { id: 'analysis_crew', label: 'Analysis', icon: Search },
  { id: 'synthesis', label: 'Synthesis', icon: FileText },
  { id: 'critic', label: 'Critique', icon: Target },
]

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
    <div className="min-h-[calc(100vh-4rem)] bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950/20 text-slate-200 p-4 md:p-8 selection:bg-indigo-500/30">
      <div className="max-w-4xl mx-auto">
        <motion.div 
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-10 text-center"
        >
          <div className="inline-flex items-center justify-center p-3 rounded-2xl bg-indigo-500/10 mb-4 border border-indigo-500/20 shadow-[0_0_30px_rgba(99,102,241,0.2)]">
            <Network className="w-8 h-8 text-indigo-400" />
          </div>
          <h1 className="text-4xl md:text-5xl font-extrabold mb-3 tracking-tight">
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-purple-400 to-indigo-400 animate-gradient-x">
              Deep Reasoning
            </span>
          </h1>
          <p className="text-slate-400 text-lg max-w-2xl mx-auto font-light">
            Parallel multi-agent analysis grounded in the SYNAPSE knowledge graph
          </p>
        </motion.div>

        <motion.div 
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1 }}
          className="mb-8 relative group"
        >
          <div className="absolute -inset-1 bg-gradient-to-r from-indigo-500 to-purple-600 rounded-2xl blur opacity-25 group-hover:opacity-40 transition duration-500"></div>
          <div className="relative bg-slate-900/80 backdrop-blur-xl border border-white/10 rounded-2xl p-2 shadow-2xl overflow-hidden flex flex-col transition-all">
            <textarea
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && e.ctrlKey) submitQuery() }}
              placeholder="Ask a deep analytical question... e.g. How have the trade-offs of current DeepSeek models decreased compared to the first versions?"
              rows={4}
              className="w-full bg-transparent p-4 text-white placeholder-slate-500 resize-none focus:outline-none text-lg"
              disabled={loading}
            />
            <div className="flex justify-between items-center p-2 border-t border-white/5 bg-slate-950/50 mt-1 rounded-xl">
              <span className="text-xs text-slate-500 flex items-center gap-1.5 px-2">
                <kbd className="px-1.5 py-0.5 bg-slate-800 rounded border border-slate-700 font-sans">Ctrl</kbd> + <kbd className="px-1.5 py-0.5 bg-slate-800 rounded border border-slate-700 font-sans">Enter</kbd> to submit
              </span>
              <button
                onClick={submitQuery}
                disabled={loading || !query.trim()}
                className="px-6 py-2.5 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 disabled:from-slate-800 disabled:to-slate-800 disabled:text-slate-500 text-white font-medium rounded-lg transition-all shadow-lg shadow-indigo-900/20 flex items-center gap-2 cursor-pointer disabled:cursor-not-allowed"
              >
                {loading ? (
                  <>
                    <Activity className="w-4 h-4 animate-spin" />
                    Analyzing
                  </>
                ) : (
                  <>
                    <Zap className="w-4 h-4" />
                    Submit Query
                  </>
                )}
              </button>
            </div>
          </div>
        </motion.div>

        <AnimatePresence>
          {loading && (
            <motion.div 
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-10 overflow-hidden"
            >
              <div className="flex flex-wrap gap-3 justify-center items-center py-4 px-2">
                {STAGES.map((stage, i) => {
                  const Icon = stage.icon
                  const isActive = i === stageIndex
                  const isPast = i < stageIndex
                  // Handle parallel layout trick visually: If current node is analysis_crew, web_research and retrieval should both look past.
                  return (
                    <motion.div 
                      key={stage.id} 
                      layout
                      transition={{ type: "spring", stiffness: 500, damping: 30 }}
                      className={`relative flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all duration-300 ${
                        isPast ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                        isActive ? 'bg-indigo-600 text-white shadow-[0_0_20px_rgba(99,102,241,0.6)] border border-indigo-400/50 scale-105 z-10' :
                        'bg-slate-800/50 text-slate-500 border border-slate-700/50'
                      }`}
                    >
                      {isActive && (
                        <motion.div
                          layoutId="active-glow"
                          className="absolute inset-0 rounded-xl bg-indigo-500/20 blur-md -z-10"
                        />
                      )}
                      <Icon className={`w-4 h-4 ${isPast ? 'text-emerald-500' : isActive ? 'text-white' : 'text-slate-600'}`} />
                      {stage.label}
                      {isActive && <motion.span animate={{ opacity: [0, 1, 0] }} transition={{ repeat: Infinity, duration: 1 }} className="ml-1 w-1.5 h-1.5 rounded-full bg-white block shadow-[0_0_5px_white]" />}
                    </motion.div>
                  )
                })}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {error && (
          <motion.div 
            initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
            className="bg-red-500/10 border border-red-500/30 rounded-2xl p-4 text-red-400 mb-8 flex items-start gap-3 backdrop-blur-sm shadow-[0_0_15px_rgba(239,68,68,0.15)]"
          >
            <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
            <div>
              <h3 className="font-semibold mb-1">Pipeline Failed</h3>
              <p className="text-sm opacity-80">{error}</p>
            </div>
          </motion.div>
        )}

        {status === 'COMPLETE' && result && (
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-6"
          >
            {/* Meta badges */}
            <div className="flex gap-3 text-xs flex-wrap">
              {result.retrieval_confidence !== undefined && (
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/50 border border-slate-700/50 text-slate-300 shadow-inner">
                  <Target className="w-3.5 h-3.5 text-indigo-400" />
                  Graph Confidence: <strong className="text-white">{(result.retrieval_confidence * 100).toFixed(0)}%</strong>
                </div>
              )}
              {result.web_research_used && (
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-300 shadow-inner">
                  <Globe className="w-3.5 h-3.5" />
                  Web Research Applied
                </div>
              )}
              {result.model_trace && (
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/50 border border-slate-700/50 text-slate-300 shadow-inner">
                  <BrainCircuit className="w-3.5 h-3.5 text-purple-400" />
                  Agents: <strong className="text-white">{Object.values(result.model_trace).join(', ')}</strong>
                </div>
              )}
            </div>

            {/* RAGAS Eval */}
            {result.ragas_eval && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                {[
                  { label: 'Faithfulness', val: result.ragas_eval.faithfulness },
                  { label: 'Relevancy', val: result.ragas_eval.answer_relevancy },
                  { label: 'Precision', val: result.ragas_eval.context_precision },
                  { label: 'Recall', val: result.ragas_eval.context_recall }
                ].map((metric, idx) => {
                  const isGood = metric.val >= 0.8;
                  const isOk = metric.val >= 0.5;
                  return (
                    <div key={idx} className="flex flex-col gap-1 p-3 rounded-xl bg-slate-900/50 border border-slate-800 backdrop-blur-sm shadow-md">
                      <span className="text-slate-400 uppercase tracking-wider text-[10px] font-semibold">{metric.label}</span>
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className={`w-4 h-4 ${isGood ? 'text-emerald-500' : isOk ? 'text-amber-500' : 'text-red-500'}`} />
                        <strong className={`text-lg ${isGood ? 'text-emerald-400 drop-shadow-[0_0_8px_rgba(52,211,153,0.5)]' : isOk ? 'text-amber-400' : 'text-red-400'}`}>
                          {(metric.val * 100).toFixed(0)}%
                        </strong>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            {/* Synthesis Content */}
            <div className="bg-slate-900/80 backdrop-blur-xl border border-white/10 rounded-2xl p-6 md:p-10 shadow-[0_10px_40px_-10px_rgba(0,0,0,0.5)] relative overflow-hidden group">
              <div className="absolute top-0 right-0 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none -translate-y-1/2 translate-x-1/3 group-hover:bg-indigo-500/20 transition-colors duration-1000"></div>
              <div className="prose prose-invert prose-indigo max-w-none text-slate-300 leading-relaxed prose-headings:text-white prose-a:text-indigo-400 hover:prose-a:text-indigo-300 prose-pre:bg-slate-950/80 prose-pre:border prose-pre:border-slate-800/80 prose-pre:shadow-inner prose-strong:text-white prose-strong:font-semibold" 
                dangerouslySetInnerHTML={{ __html: renderMarkdown(result.synthesis_markdown || result.markdown || '') }} 
              />
            </div>

            {/* Citations & Gaps */}
            <div className="grid md:grid-cols-2 gap-6">
              {result.sources && result.sources.length > 0 && (
                <div className="bg-slate-900/50 backdrop-blur-sm border border-slate-800/80 rounded-2xl p-6 shadow-lg">
                  <h3 className="text-white font-semibold mb-4 flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Grounding Sources
                  </h3>
                  <div className="space-y-3 text-sm max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                    {result.sources.map((s, i) => (
                      <div key={i} className="flex gap-3 group/src">
                        <span className="text-emerald-500/50 font-mono text-xs mt-0.5">[{i + 1}]</span>
                        <div>
                          {s.url ? (
                            <a href={s.url} target="_blank" rel="noopener" className="text-slate-300 group-hover/src:text-emerald-400 transition-colors font-medium">
                              {s.title || s.url}
                            </a>
                          ) : (
                            <span className="text-slate-300 font-medium">{s.title}</span>
                          )}
                          {s.source && <span className="ml-2 text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded uppercase tracking-wider">{s.source}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {result.gaps && result.gaps.length > 0 && (
                <div className="bg-amber-950/20 backdrop-blur-sm border border-amber-900/30 rounded-2xl p-6 shadow-lg">
                  <h3 className="text-amber-400 font-semibold mb-4 flex items-center gap-2">
                    <Search className="w-4 h-4" /> Knowledge Gaps
                  </h3>
                  <ul className="space-y-2 text-sm text-amber-200/80 list-disc list-inside">
                    {result.gaps.map((gap, i) => (
                      <li key={i} className="leading-snug">{gap}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

          </motion.div>
        )}
      </div>
    </div>
  )
}

function renderMarkdown(md: string): string {
  if (!md) return ''
  let html = md
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-slate-950/90 p-5 rounded-xl text-sm overflow-x-auto my-5 border border-slate-800 shadow-inner text-slate-300 font-mono"><code>$2</code></pre>')
    .replace(/`([^`]+)`/g, '<code class="bg-indigo-500/10 text-indigo-300 px-1.5 py-0.5 rounded text-sm border border-indigo-500/20 font-mono">$1</code>')
    .replace(/^### (.+)$/gm, '<h3 class="text-xl font-bold mt-8 mb-4 text-white flex items-center gap-2"><span class="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block"></span> $1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-2xl font-extrabold mt-10 mb-5 text-transparent bg-clip-text bg-gradient-to-r from-white to-slate-400">$1</h2>')
    .replace(/^- (.+)$/gm, '<li class="ml-4 mb-2 flex items-start"><span class="mr-2 text-indigo-500 mt-1.5 text-[10px]">■</span> <span>$1</span></li>')
    .replace(/\n\n/g, '<br/><br/>')
  
  html = html.replace(/\|(.+)\|\n\|[-| ]+\|\n((?:\|.+\|\n?)*)/g, (_, header, rows) => {
    const hcols = header.split('|').filter((c: string) => c.trim()).map((c: string) => `<th class="border-b border-slate-700 px-5 py-4 text-left font-semibold text-slate-200 bg-slate-800/80 tracking-wide">${c.trim()}</th>`).join('')
    const rrows = rows.trim().split('\n').map((row: string) => {
      const cols = row.split('|').filter((c: string) => c.trim()).map((c: string) => `<td class="border-b border-slate-800 px-5 py-3 text-slate-300">${c.trim()}</td>`).join('')
      return `<tr class="hover:bg-slate-800/40 transition-colors">${cols}</tr>`
    }).join('')
    return `<div class="overflow-x-auto my-8 rounded-xl border border-slate-700/60 shadow-lg"><table class="w-full border-collapse text-sm text-slate-300"><thead><tr>${hcols}</tr></thead><tbody>${rrows}</tbody></table></div>`
  })
  
  return DOMPurify.sanitize(html, { ALLOWED_TAGS: ['h2', 'h3', 'p', 'br', 'strong', 'em', 'code', 'pre', 'li', 'ul', 'ol', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'a', 'span', 'div'], ALLOWED_ATTR: ['class', 'href', 'target', 'rel'] })
}
