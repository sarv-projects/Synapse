import React, { useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Search, MessageSquare, Network,
  GitCompare, Trophy, ShieldCheck, Download,
  Info, Menu, X, Zap, Brain, Upload
} from 'lucide-react'

const NAV = [
  { name: 'Dashboard',   href: '/',            icon: LayoutDashboard },
  { name: 'Search',      href: '/search',      icon: Search },
  { name: 'Ask',         href: '/ask',         icon: MessageSquare },
  { name: 'Reason',      href: '/reason',      icon: Brain },
  { name: 'Graph',       href: '/graph',       icon: Network },
  { name: 'Ingest',      href: '/ingest',      icon: Upload },
  { name: 'Diff',        href: '/diff',        icon: GitCompare },
  { name: 'Leaderboard', href: '/leaderboard', icon: Trophy },
  { name: 'Quality',     href: '/quality',     icon: ShieldCheck },
  { name: 'Export',      href: '/export',      icon: Download },
  { name: 'About',       href: '/about',       icon: Info },
]

export function Layout() {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)

  return (
    <div className="min-h-screen bg-slate-50 text-gray-900">

      {/* ── Navbar ─────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-50 bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-screen-xl mx-auto px-4 sm:px-6 flex items-center justify-between h-14">

          {/* Logo */}
          <Link to="/" className="flex items-center gap-2 shrink-0">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center shadow-md shadow-indigo-200">
              <Zap className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-gray-900 text-lg">SYNAPSE</span>
            <span className="hidden md:block text-xs text-gray-400 font-normal border-l border-gray-200 pl-2 ml-1">
              AI Knowledge Graph
            </span>
          </Link>

          {/* Desktop nav */}
          <nav className="hidden lg:flex items-center gap-0.5">
            {NAV.map(({ name, href, icon: Icon }) => {
              const active = pathname === href
              return (
                <Link key={href} to={href}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-150 ${
                    active
                      ? 'bg-indigo-50 text-indigo-700 shadow-sm'
                      : 'text-gray-500 hover:text-gray-900 hover:bg-gray-100'
                  }`}>
                  <Icon className={`w-3.5 h-3.5 ${active ? 'text-indigo-600' : ''}`} />
                  {name}
                </Link>
              )
            })}
          </nav>

          {/* Mobile toggle */}
          <button onClick={() => setOpen(o => !o)}
            className="lg:hidden p-2 rounded-lg text-gray-500 hover:bg-gray-100 transition-colors">
            {open ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>

        {/* Mobile menu */}
        {open && (
          <div className="lg:hidden border-t border-gray-100 bg-white px-4 py-3 grid grid-cols-2 gap-1 animate-fadeIn">
            {NAV.map(({ name, href, icon: Icon }) => {
              const active = pathname === href
              return (
                <Link key={href} to={href} onClick={() => setOpen(false)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    active ? 'bg-indigo-50 text-indigo-700' : 'text-gray-600 hover:bg-gray-100'
                  }`}>
                  <Icon className="w-4 h-4" />{name}
                </Link>
              )
            })}
          </div>
        )}
      </header>

      {/* ── Content ────────────────────────────────────────────────────── */}
      <main className="max-w-screen-xl mx-auto px-4 sm:px-6 py-8 animate-fadeIn">
        <Outlet />
      </main>
    </div>
  )
}
