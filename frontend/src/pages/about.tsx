import React from 'react'
import { Brain, Github, Zap } from 'lucide-react'

export function About() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Brain className="w-6 h-6 text-indigo-500" /> About SYNAPSE
        </h1>
        <p className="text-gray-600 dark:text-gray-400 mt-2 leading-relaxed">
          <strong>SYNAPSE</strong> — Systematic, Networked, Yet Natural, Automated, Provenance-aware Schema Engine —
          is a live, open-access knowledge graph for the AI ecosystem. Every relationship carries a birth certificate:
          extraction method, evidence URL, confidence score, and verification status.
        </p>
      </div>

      <div className="bg-white rounded-lg shadow p-6 space-y-4">
        <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
          <Zap className="w-5 h-5 text-indigo-500" /> What SYNAPSE can do
        </h2>
        <div className="space-y-3">
          {[
            {
              icon: '🔍',
              title: 'Ask in plain English',
              body: 'Type a question like "Which tools implement transformers?" and get real answers from the graph — no query language needed.',
            },
            {
              icon: '🕸️',
              title: 'Explore the AI ecosystem as a graph',
              body: 'See how papers, models, tools, techniques, and organizations connect to each other — not just a list, but a living network.',
            },
            {
              icon: '📅',
              title: 'Track what changed over time',
              body: 'Compare the AI landscape between any two dates. See what was added, what grew, and what disappeared.',
            },
            {
              icon: '✅',
              title: 'Every fact is traceable',
              body: 'Every relationship in the graph carries where it came from, how confident we are, and when it was last verified.',
            },
            {
              icon: '⚡',
              title: 'Always fresh, always free',
              body: 'The graph updates every morning from 9 live data sources. No login, no account, no paywall — ever.',
            },
            {
              icon: '📤',
              title: 'Export for your own research',
              body: 'Download any subgraph as JSON-LD, CSV, or GraphML and use it in your own tools, notebooks, or papers.',
            },
          ].map(f => (
            <div key={f.title} className="flex gap-3">
              <span className="text-xl shrink-0 mt-0.5">{f.icon}</span>
              <div>
                <p className="text-sm font-semibold text-gray-900">{f.title}</p>
                <p className="text-sm text-gray-500 mt-0.5 leading-relaxed">{f.body}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <p className="text-sm text-gray-500">
          Built by <strong className="text-gray-900 dark:text-white">Sarvesh Bhattacharyya</strong>, Bengaluru · May 2026
        </p>
        <a href="https://github.com" target="_blank" rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 mt-2 text-sm text-indigo-600 dark:text-indigo-400 hover:underline">
          <Github className="w-4 h-4" /> View on GitHub
        </a>
      </div>
    </div>
  )
}
