import React from 'react'
import ReactDOM from 'react-dom/client'
import { createBrowserRouter, RouterProvider, Link } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Layout } from '@/components/layout'
import { Dashboard } from '@/pages/dashboard'
import { Search } from '@/pages/search'
import { Ask } from '@/pages/ask'
import { GraphExplorer } from '@/pages/graph'
import { Diff } from '@/pages/diff'
import { Leaderboard } from '@/pages/leaderboard'
import { Quality } from '@/pages/quality'
import { Export } from '@/pages/export'
import { Docs } from '@/pages/docs'
import { About } from '@/pages/about'
import Reason from '@/pages/reason'
import Ingest from '@/pages/ingest'
import Budget from '@/pages/budget'

import '@/styles/globals.css'

// ── 404 page ─────────────────────────────────────────────────────────────────
function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <h1 className="text-6xl font-bold text-indigo-600 mb-4">404</h1>
      <p className="text-xl text-gray-700 mb-6">Page not found</p>
      <Link to="/" className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">
        Back to Dashboard
      </Link>
    </div>
  )
}

// ── Query client ──────────────────────────────────────────────────────────────
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

// ── Router ────────────────────────────────────────────────────────────────────
const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true,          element: <Dashboard /> },
      { path: 'search',       element: <Search /> },
      { path: 'ask',          element: <Ask /> },
      { path: 'graph',        element: <GraphExplorer /> },
      { path: 'graph/:entity',element: <GraphExplorer /> },
      { path: 'diff',         element: <Diff /> },
      { path: 'leaderboard',  element: <Leaderboard /> },
      { path: 'quality',      element: <Quality /> },
      { path: 'export',       element: <Export /> },
      { path: 'docs',         element: <Docs /> },
      { path: 'about',        element: <About /> },
      { path: 'reason',       element: <Reason /> },
      { path: 'ingest',       element: <Ingest /> },
      { path: 'budget',       element: <Budget /> },
      { path: '*',            element: <NotFound /> },
    ],
  },
])

// ── App ───────────────────────────────────────────────────────────────────────
function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

// ── Mount — no StrictMode (prevents double-render in dev) ─────────────────────
ReactDOM.createRoot(document.getElementById('root')!).render(<App />)
