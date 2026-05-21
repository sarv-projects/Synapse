import { useState, useEffect } from 'react'

interface ModelBudget {
  rpm_remaining: number
  rpd_remaining: number
  tpm_remaining: number
  rpm_limit: number
  rpd_limit: number
  tpm_limit: number
  tokens_in_flight: number
}

interface BudgetData {
  timestamp: string
  models: Record<string, ModelBudget>
}

export default function Budget() {
  const [data, setData] = useState<BudgetData | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const fetchBudget = async () => {
      try {
        const res = await fetch('/api/v1/budget')
        const d = await res.json()
        if (d.error) setError(d.error)
        else setData(d)
      } catch (e) {
        setError(String(e))
      }
    }
    fetchBudget()
    const interval = setInterval(fetchBudget, 10000)
    return () => clearInterval(interval)
  }, [])

  const formatPct = (remaining: number, limit: number) => {
    const pct = limit > 0 ? (remaining / limit) * 100 : 0
    return pct.toFixed(0) + '%'
  }

  const barColor = (remaining: number, limit: number) => {
    const pct = limit > 0 ? remaining / limit : 0
    if (pct > 0.5) return 'bg-emerald-500'
    if (pct > 0.2) return 'bg-amber-500'
    return 'bg-red-500'
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-2">Token Budget Dashboard</h1>
      <p className="text-slate-400 mb-6">Per-model rate limit status — updates every 10 seconds</p>

      {error && <div className="bg-red-900/30 border border-red-800 rounded-lg p-3 text-red-300 mb-4">{error}</div>}

      {data && (
        <div className="space-y-4">
          <div className="text-xs text-slate-500">Last updated: {data.timestamp}</div>

          {Object.entries(data.models).map(([modelId, m]) => (
            <div key={modelId} className="bg-slate-800 border border-slate-700 rounded-lg p-4">
              <div className="flex justify-between items-center mb-3">
                <h3 className="font-mono text-sm text-white">{modelId}</h3>
                <div className="flex gap-2 text-xs">
                  <span className={`px-2 py-0.5 rounded ${m.tokens_in_flight > 0 ? 'bg-amber-700 text-amber-200' : 'bg-slate-700 text-slate-400'}`}>
                    {m.tokens_in_flight > 0 ? `${m.tokens_in_flight} in flight` : 'idle'}
                  </span>
                </div>
              </div>

              <div className="space-y-2 text-sm">
                <div>
                  <div className="flex justify-between text-slate-400 mb-1">
                    <span>RPM</span>
                    <span className="text-white font-mono">{m.rpm_remaining}/{m.rpm_limit} ({formatPct(m.rpm_remaining, m.rpm_limit)})</span>
                  </div>
                  <div className="w-full bg-slate-700 rounded-full h-2">
                    <div className={`h-2 rounded-full transition-all ${barColor(m.rpm_remaining, m.rpm_limit)}`} style={{ width: formatPct(m.rpm_remaining, m.rpm_limit) }} />
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-slate-400 mb-1">
                    <span>RPD</span>
                    <span className="text-white font-mono">{m.rpd_remaining}/{m.rpd_limit} ({formatPct(m.rpd_remaining, m.rpd_limit)})</span>
                  </div>
                  <div className="w-full bg-slate-700 rounded-full h-2">
                    <div className={`h-2 rounded-full transition-all ${barColor(m.rpd_remaining, m.rpd_limit)}`} style={{ width: formatPct(m.rpd_remaining, m.rpd_limit) }} />
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-slate-400 mb-1">
                    <span>TPM</span>
                    <span className="text-white font-mono">{m.tpm_remaining.toLocaleString()}/{m.tpm_limit.toLocaleString()} ({formatPct(m.tpm_remaining, m.tpm_limit)})</span>
                  </div>
                  <div className="w-full bg-slate-700 rounded-full h-2">
                    <div className={`h-2 rounded-full transition-all ${barColor(m.tpm_remaining, m.tpm_limit)}`} style={{ width: formatPct(m.tpm_remaining, m.tpm_limit) }} />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
