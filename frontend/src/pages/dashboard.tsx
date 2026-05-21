import React, { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Network, Zap, TrendingUp, ArrowRight,
  CheckCircle, AlertTriangle, Activity, Database,
  Search, MessageSquare, GitCompare, Trophy, Sparkles
} from 'lucide-react'
import { Reveal } from '@/components/Reveal'

// ── Animated counter ──────────────────────────────────────────────────────────
function CountUp({ to, duration = 1400 }: { to: number; duration?: number }) {
  const [val, setVal] = useState(0)
  const raf = useRef<number | null>(null)
  useEffect(() => {
    if (!to) return
    const start = performance.now()
    const tick = (now: number) => {
      const p = Math.min((now - start) / duration, 1)
      const eased = 1 - Math.pow(1 - p, 3)
      setVal(Math.round(eased * to))
      if (p < 1) raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => { if (raf.current) cancelAnimationFrame(raf.current) }
  }, [to, duration])
  return <>{val.toLocaleString()}</>
}

// ── Skeleton ──────────────────────────────────────────────────────────────────
function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse bg-gray-200 rounded-lg ${className}`} />
}

// ── Live dot ──────────────────────────────────────────────────────────────────
function LiveDot() {
  return (
    <span className="relative flex h-2 w-2">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
      <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
    </span>
  )
}

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ icon: Icon, label, value, sub, accent, loading, delay = 0 }: {
  icon: React.ElementType; label: string; value?: number
  sub?: string; accent: string; loading?: boolean; delay?: number
}) {
  return (
    <Reveal direction="up" delay={delay}>
      <div className="group bg-white rounded-2xl border border-gray-100 shadow-sm p-5
                      hover:shadow-lg hover:-translate-y-1 transition-all duration-300 cursor-default">
        <div className="flex items-start justify-between mb-4">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">{label}</p>
          <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${accent}
                          group-hover:scale-110 transition-transform duration-300`}>
            <Icon className="w-[18px] h-[18px] text-white" />
          </div>
        </div>
        {loading
          ? <Skeleton className="h-8 w-24 mb-1" />
          : <p className="text-3xl font-bold text-gray-900 tabular-nums">
              {value != null ? <CountUp to={value} /> : '—'}
            </p>
        }
        {sub && <p className="mt-1 text-xs text-gray-400">{sub}</p>}
      </div>
    </Reveal>
  )
}

// ── Action card ───────────────────────────────────────────────────────────────
function ActionCard({ href, icon: Icon, label, sub, accent, delay = 0 }: {
  href: string; icon: React.ElementType; label: string
  sub: string; accent: string; delay?: number
}) {
  return (
    <Reveal direction="up" delay={delay}>
      <Link to={href}
        className="group flex items-center gap-4 p-4 bg-white rounded-2xl border border-gray-100
                   shadow-sm hover:shadow-md hover:-translate-y-1 transition-all duration-300">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${accent}
                        group-hover:scale-110 transition-transform duration-300`}>
          <Icon className="w-5 h-5 text-white" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-gray-900">{label}</p>
          <p className="text-xs text-gray-400 mt-0.5">{sub}</p>
        </div>
        <ArrowRight className="w-4 h-4 text-gray-300 group-hover:text-indigo-500
                               group-hover:translate-x-1 transition-all duration-200 shrink-0" />
      </Link>
    </Reveal>
  )
}

// ── Infinite source ticker ────────────────────────────────────────────────────
const SOURCES = [
  'arXiv', 'HuggingFace Hub', 'HF Daily Papers', 'GitHub Trending',
  'Papers With Code', 'Semantic Scholar', 'OpenAlex', 'DAIR.AI', 'Kaggle',
  'arXiv', 'HuggingFace Hub', 'HF Daily Papers', 'GitHub Trending',
  'Papers With Code', 'Semantic Scholar', 'OpenAlex', 'DAIR.AI', 'Kaggle',
]

function SourceTicker() {
  return (
    <div className="overflow-hidden relative">
      {/* fade edges */}
      <div className="absolute left-0 top-0 bottom-0 w-16 bg-gradient-to-r from-slate-50 to-transparent z-10 pointer-events-none" />
      <div className="absolute right-0 top-0 bottom-0 w-16 bg-gradient-to-l from-slate-50 to-transparent z-10 pointer-events-none" />
      <div className="flex gap-3 animate-ticker w-max">
        {SOURCES.map((src, i) => (
          <div key={i} className="flex items-center gap-1.5 px-3 py-1.5 bg-white rounded-full
                                  border border-gray-200 shadow-sm whitespace-nowrap shrink-0">
            <LiveDot />
            <span className="text-xs font-medium text-gray-600">{src}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
export function Dashboard() {
  const { data: health, isLoading } = useQuery({
    queryKey: ['health'],
    queryFn: () => fetch('/api/v1/health').then(r => r.json()),
    refetchInterval: 30000,
  })

  return (
    <div className="space-y-12">

      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden rounded-3xl bg-white border border-gray-100 shadow-sm px-8 py-12 sm:py-16">

        {/* Floating gradient orbs */}
        <div className="absolute -top-20 -right-20 w-80 h-80 bg-indigo-100 rounded-full blur-3xl opacity-60 animate-float pointer-events-none" />
        <div className="absolute -bottom-16 -left-16 w-64 h-64 bg-purple-100 rounded-full blur-3xl opacity-50 animate-float-slow pointer-events-none" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-32 bg-sky-50 rounded-full blur-3xl opacity-40 pointer-events-none" />

        <div className="relative flex flex-col sm:flex-row sm:items-center justify-between gap-8">
          <div className="max-w-xl">
            {/* Live badge */}
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-50
                            border border-emerald-200 mb-5 animate-fadeIn">
              <LiveDot />
              <span className="text-xs font-semibold text-emerald-700 uppercase tracking-wider">Live · Updates daily</span>
            </div>

            {/* Gradient headline */}
            <h1 className="text-4xl sm:text-5xl font-extrabold leading-tight mb-4 animate-slideUp">
              <span className="bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-500
                               bg-clip-text text-transparent">
                AI Knowledge
              </span>
              <br />
              <span className="text-gray-900">Graph, Live.</span>
            </h1>

            <p className="text-gray-500 text-base leading-relaxed animate-slideUp" style={{ animationDelay: '100ms' }}>
              Every relationship carries its source, confidence score, and evidence snippet.
              Ingested daily from 9 free-tier APIs — no login required.
            </p>
          </div>

          {/* CTA buttons */}
          <div className="flex flex-row sm:flex-col gap-3 shrink-0 animate-slideUp" style={{ animationDelay: '200ms' }}>
            <Link to="/ask"
              className="group flex items-center gap-2 px-5 py-3 bg-indigo-600 hover:bg-indigo-700
                         text-white text-sm font-semibold rounded-xl transition-all duration-200
                         shadow-lg shadow-indigo-200 hover:shadow-indigo-300 hover:-translate-y-0.5">
              <Zap className="w-4 h-4 group-hover:animate-pulse" />
              Ask SYNAPSE
            </Link>
            <Link to="/search"
              className="flex items-center gap-2 px-5 py-3 bg-gray-50 hover:bg-gray-100
                         text-gray-700 text-sm font-semibold rounded-xl transition-all duration-200
                         border border-gray-200 hover:-translate-y-0.5">
              <Search className="w-4 h-4" />
              Search Graph
            </Link>
          </div>
        </div>
      </section>

      {/* ── Stats ─────────────────────────────────────────────────────────── */}
      <section>
        <Reveal direction="fade">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-5">
            Graph at a glance
          </p>
        </Reveal>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard loading={isLoading} icon={Network}    label="Total Nodes"  value={health?.total_nodes}           sub="in knowledge graph"  accent="bg-indigo-500"  delay={0} />
          <StatCard loading={isLoading} icon={Activity}   label="Total Edges"  value={health?.total_edges}           sub="relationships"       accent="bg-violet-500"  delay={80} />
          <StatCard loading={isLoading} icon={TrendingUp} label="New Today"    value={health?.today_entities}        sub="entities added"      accent="bg-emerald-500" delay={160} />
          <StatCard loading={isLoading} icon={Database}   label="Embeddings"   value={health?.nodes_with_embeddings} sub="384-dim vectors"     accent="bg-sky-500"     delay={240} />
        </div>
      </section>

      {/* ── System status ─────────────────────────────────────────────────── */}
      <Reveal direction="up">
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 flex items-center gap-4">
          {isLoading
            ? <Skeleton className="h-8 w-48" />
            : <>
                {health?.status === 'healthy'
                  ? <CheckCircle className="w-6 h-6 text-emerald-500 shrink-0" />
                  : <AlertTriangle className="w-6 h-6 text-orange-500 shrink-0" />}
                <div>
                  <span className="font-semibold text-gray-900 capitalize">{health?.status ?? 'Unknown'}</span>
                  <span className="text-gray-400 text-sm ml-2">· v{health?.version ?? '3.0.0'}</span>
                </div>
                <div className="ml-auto flex items-center gap-1.5">
                  <Sparkles className="w-4 h-4 text-indigo-400" />
                  <span className="text-xs text-gray-400">Powered by Neo4j · Groq · Qdrant</span>
                </div>
              </>
          }
        </div>
      </Reveal>

      {/* ── Quick actions ─────────────────────────────────────────────────── */}
      <section>
        <Reveal direction="fade">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-5">
            Quick actions
          </p>
        </Reveal>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <ActionCard href="/ask"         icon={MessageSquare} label="Ask a question"  sub="Natural language → Cypher"  accent="bg-indigo-500"  delay={0} />
          <ActionCard href="/search"      icon={Search}        label="Search entities" sub="Papers, models, tools"      accent="bg-violet-500"  delay={60} />
          <ActionCard href="/diff"        icon={GitCompare}    label="What changed?"   sub="Temporal knowledge diff"    accent="bg-emerald-500" delay={120} />
          <ActionCard href="/leaderboard" icon={Trophy}        label="Leaderboards"    sub="Top tools & papers"         accent="bg-sky-500"     delay={180} />
        </div>
      </section>

      {/* ── Live sources ticker ───────────────────────────────────────────── */}
      <Reveal direction="up">
        <section>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">
            Live data sources
          </p>
          <SourceTicker />
        </section>
      </Reveal>

      {/* ── Feature highlights ────────────────────────────────────────────── */}
      <section className="grid sm:grid-cols-3 gap-4">
        {[
          {
            icon: '🔗',
            title: 'Provenance on every edge',
            body: 'Every relationship carries extraction method, evidence URL, confidence score, and verification date.',
            delay: 0,
          },
          {
            icon: '🧠',
            title: 'Natural language queries',
            body: 'Ask in plain English. Llama 4 Scout translates to Cypher, validates it, and returns results with evidence.',
            delay: 100,
          },
          {
            icon: '⚡',
            title: 'Daily auto-ingestion',
            body: 'GitHub Actions runs the pipeline every morning at 5:30 AM IST across 9 free-tier APIs.',
            delay: 200,
          },
        ].map(({ icon, title, body, delay }) => (
          <Reveal key={title} direction="up" delay={delay}>
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6
                            hover:shadow-md hover:-translate-y-1 transition-all duration-300">
              <div className="text-3xl mb-3">{icon}</div>
              <h3 className="font-semibold text-gray-900 mb-2">{title}</h3>
              <p className="text-sm text-gray-500 leading-relaxed">{body}</p>
            </div>
          </Reveal>
        ))}
      </section>

    </div>
  )
}
