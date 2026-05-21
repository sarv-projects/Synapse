import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { ShieldCheck, AlertTriangle, CheckCircle, BarChart3, Target, Crosshair, Brain } from 'lucide-react'

export function Quality() {
  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ['quality'],
    queryFn: async () => {
      const res = await fetch('/api/v1/health')
      if (!res.ok) throw new Error('Failed to fetch health')
      return res.json()
    },
    refetchInterval: 60000,
  })

  const { data: evalData, isLoading: evalLoading } = useQuery({
    queryKey: ['eval'],
    queryFn: async () => {
      const res = await fetch('/api/v1/eval')
      if (!res.ok) throw new Error('Failed to fetch eval metrics')
      return res.json()
    },
    refetchInterval: 30000,
  })

  const scoreColor = (v: number) =>
    v >= 0.80 ? 'text-emerald-400' : v >= 0.50 ? 'text-amber-400' : 'text-red-400'

  const barWidth = (v: number) => `${Math.min(100, Math.round(v * 100))}%`

  if (healthLoading && evalLoading) return <div className="text-center py-12 text-gray-500">Loading…</div>

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <ShieldCheck className="w-6 h-6 text-green-500" /> Quality & Health
        </h1>
        <p className="text-gray-600 dark:text-gray-400 mt-1">System health, RAGAS eval metrics, and source status.</p>
      </div>

      {health && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">System Status</h2>
          <div className="flex items-center gap-2">
            {health.status === 'healthy'
              ? <CheckCircle className="w-5 h-5 text-green-500" />
              : <AlertTriangle className="w-5 h-5 text-orange-500" />}
            <span className="font-medium capitalize text-gray-900 dark:text-white">{health.status}</span>
            <span className="text-sm text-gray-500">v{health.version}</span>
          </div>
        </div>
      )}

      {evalData && !evalData.error && (
        <>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-indigo-500" /> RAGAS Evaluation Metrics
            </h2>
            <p className="text-xs text-gray-500 mb-4">
              {evalData.total_runs} runs tracked · LLM-as-judge using Groq 8B
            </p>

            <div className="grid grid-cols-2 gap-4">
              <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Brain className="w-4 h-4 text-purple-400" />
                  <span className="text-sm text-gray-500">Faithfulness</span>
                </div>
                <p className={`text-2xl font-bold ${scoreColor(evalData.avg_faithfulness)}`}>
                  {(evalData.avg_faithfulness * 100).toFixed(0)}%
                </p>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 mt-2">
                  <div className="bg-purple-500 h-1.5 rounded-full transition-all" style={{ width: barWidth(evalData.avg_faithfulness) }} />
                </div>
              </div>
              <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Target className="w-4 h-4 text-blue-400" />
                  <span className="text-sm text-gray-500">Answer Relevancy</span>
                </div>
                <p className={`text-2xl font-bold ${scoreColor(evalData.avg_answer_relevancy)}`}>
                  {(evalData.avg_answer_relevancy * 100).toFixed(0)}%
                </p>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 mt-2">
                  <div className="bg-blue-500 h-1.5 rounded-full transition-all" style={{ width: barWidth(evalData.avg_answer_relevancy) }} />
                </div>
              </div>
              <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Crosshair className="w-4 h-4 text-emerald-400" />
                  <span className="text-sm text-gray-500">Context Precision</span>
                </div>
                <p className={`text-2xl font-bold ${scoreColor(evalData.avg_context_precision)}`}>
                  {(evalData.avg_context_precision * 100).toFixed(0)}%
                </p>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 mt-2">
                  <div className="bg-emerald-500 h-1.5 rounded-full transition-all" style={{ width: barWidth(evalData.avg_context_precision) }} />
                </div>
              </div>
              <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Target className="w-4 h-4 text-amber-400" />
                  <span className="text-sm text-gray-500">Context Recall</span>
                </div>
                <p className={`text-2xl font-bold ${scoreColor(evalData.avg_context_recall)}`}>
                  {(evalData.avg_context_recall * 100).toFixed(0)}%
                </p>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 mt-2">
                  <div className="bg-amber-500 h-1.5 rounded-full transition-all" style={{ width: barWidth(evalData.avg_context_recall) }} />
                </div>
              </div>
            </div>
          </div>

          {evalData.last_10 && evalData.last_10.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
              <h3 className="text-md font-semibold text-gray-900 dark:text-white mb-3">Recent Evaluations</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-gray-500 border-b border-gray-200 dark:border-gray-700">
                      <th className="pb-2 font-medium">Query</th>
                      <th className="pb-2 font-medium">Faith</th>
                      <th className="pb-2 font-medium">Relev</th>
                      <th className="pb-2 font-medium">Prec</th>
                      <th className="pb-2 font-medium">Recall</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evalData.last_10.slice().reverse().map((s: Record<string, unknown>, i: number) => (
                      <tr key={i} className="border-b border-gray-100 dark:border-gray-800">
                        <td className="py-2 text-gray-700 dark:text-gray-300 max-w-xs truncate">{String(s.query)}</td>
                        <td className={`py-2 ${scoreColor(Number(s.faithfulness))}`}>{(Number(s.faithfulness) * 100).toFixed(0)}%</td>
                        <td className={`py-2 ${scoreColor(Number(s.relevancy))}`}>{(Number(s.relevancy) * 100).toFixed(0)}%</td>
                        <td className={`py-2 ${scoreColor(Number(s.precision))}`}>{(Number(s.precision) * 100).toFixed(0)}%</td>
                        <td className={`py-2 ${scoreColor(Number(s.recall))}`}>{(Number(s.recall) * 100).toFixed(0)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
