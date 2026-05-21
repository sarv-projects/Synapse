import React from 'react'
import { BookOpen, ExternalLink } from 'lucide-react'

export function Docs() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <BookOpen className="w-6 h-6" /> API Documentation
        </h1>
        <p className="text-gray-600 dark:text-gray-400 mt-1">
          Interactive API explorer powered by FastAPI.
        </p>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 space-y-4">
        <a href="/docs" target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-2 text-indigo-600 dark:text-indigo-400 hover:underline font-medium">
          <ExternalLink className="w-4 h-4" /> Open Swagger UI (full interactive docs)
        </a>

        <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">Quick Reference</h2>
          <div className="space-y-2 font-mono text-sm">
            {[
              ['GET', '/api/v1/health', 'System health & pipeline status'],
              ['GET', '/api/v1/search?q=&type=&cursor=', 'Full-text + vector search'],
              ['POST', '/api/v1/query', 'Natural language → Cypher'],
              ['GET', '/api/v1/similar?id=&k=5', 'Semantic similarity (Qdrant)'],
              ['GET', '/api/v1/whats-new?days=1', 'New entities in last N days'],
              ['GET', '/api/v1/diff?from=&to=', 'Temporal diff between dates'],
              ['GET', '/api/v1/export?query=&format=', 'Export subgraph'],
              ['GET', '/api/v1/groq/status', 'Groq key rotation status'],
            ].map(([method, path, desc]) => (
              <div key={path} className="flex gap-3 items-start">
                <span className={`shrink-0 px-1.5 py-0.5 rounded text-xs font-bold ${
                  method === 'GET' ? 'bg-green-100 text-green-800' : 'bg-blue-100 text-blue-800'
                }`}>{method}</span>
                <span className="text-gray-800 dark:text-gray-200">{path}</span>
                <span className="text-gray-500 text-xs">{desc}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
