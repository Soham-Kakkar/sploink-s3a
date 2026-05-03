'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'

interface Session {
  session_id: string
  status: string
  created_at: string
  updated_at: string
  drift_streak?: number
  total_events?: number
  success_events?: number
  failure_events?: number
  last_action?: string | null
  last_seen?: number | null
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000'

const statusStyles: Record<string, { label: string; pill: string; accent: string; description: string }> = {
  healthy: {
    label: 'Healthy',
    pill: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    accent: 'from-emerald-50 to-lime-50',
    description: 'The session is progressing normally and still looks aligned with its baseline.',
  },
  looping: {
    label: 'Looping',
    pill: 'bg-rose-100 text-rose-800 border-rose-200',
    accent: 'from-rose-50 to-orange-50',
    description: 'Repeated variations are converging on the same dead end.',
  },
  failing: {
    label: 'Failing',
    pill: 'bg-amber-100 text-amber-900 border-amber-200',
    accent: 'from-amber-50 to-yellow-50',
    description: 'The latest attempts are failing repeatedly and need intervention.',
  },
  drifting: {
    label: 'Drifting',
    pill: 'bg-sky-100 text-sky-900 border-sky-200',
    accent: 'from-sky-50 to-cyan-50',
    description: 'The work has moved away from the original intent or file set.',
  },
}

function formatTime(value?: string | number | null) {
  if (value === null || value === undefined) return 'just now'
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value)
  if (Number.isNaN(date.getTime())) return 'just now'
  return date.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function getStatusMeta(status: string) {
  return statusStyles[status] ?? {
    label: status,
    pill: 'bg-slate-100 text-slate-700 border-slate-200',
    accent: 'from-slate-50 to-stone-50',
    description: 'No heuristic label is available for this session yet.',
  }
}

export default function Dashboard() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<string | null>(null)

  useEffect(() => {
    const fetchSessions = async () => {
      try {
        const res = await fetch(`${API_BASE}/sessions`, { cache: 'no-store' })
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`)
        }
        const data = await res.json()
        setSessions(Array.isArray(data) ? data : [])
        setError(null)
        setLastRefresh(new Date().toLocaleTimeString())
      } catch (err) {
        console.error('Failed to fetch sessions', err)
        setError('The API is offline or the backend has not started yet.')
      } finally {
        setLoading(false)
      }
    }

    fetchSessions()
    // open websocket for live sessions updates and stop polling
    let ws: WebSocket | null = null
    try {
      const base = API_BASE.replace(/^http/, 'ws')
      const url = `${base.replace(/\/$/, '')}/ws/sessions`
      ws = new WebSocket(url)
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg.sessions) {
            setSessions(Array.isArray(msg.sessions) ? msg.sessions : [])
            setError(null)
            setLastRefresh(new Date().toLocaleTimeString())
            setLoading(false)
          }
        } catch (e) {
          console.error('Malformed WS message', e)
        }
      }
      ws.onclose = () => {
        // no-op
      }
    } catch (e) {
      console.error('Failed to open websocket', e)
    }

    return () => {
      if (ws) ws.close()
    }
  }, [])

  const totalEvents = sessions.reduce((sum, session) => sum + (session.total_events ?? 0), 0)
  const healthyCount = sessions.filter((session) => session.status === 'healthy').length
  const anomalousCount = sessions.filter((session) => session.status !== 'healthy').length
  const latestUpdate = sessions.length > 0 ? Math.max(...sessions.map((session) => new Date(session.updated_at).getTime())) : null

  return (
    <div className="min-h-screen px-4 py-6 text-slate-900 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <section className="overflow-hidden rounded-4xl border border-white/60 bg-white/75 p-6 shadow-[0_20px_60px_rgba(15,23,42,0.08)] backdrop-blur sm:p-8">
          <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl space-y-4">
              <div className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.28em] text-sky-800">
                <span className="h-2 w-2 rounded-full bg-sky-500" />
                Live observability
              </div>
              <div className="space-y-3">
                <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">Agent Observability Dashboard</h1>
                <p className="max-w-2xl text-base leading-7 text-slate-600 sm:text-lg">
                  Watch agent sessions in motion, spot repeated retries, drift, and failure streaks, and open any session to inspect the full timeline.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-3 text-sm text-slate-600">
                <span className="rounded-full border border-slate-200 bg-white px-3 py-1">Polling every 3 seconds</span>
                <span className="rounded-full border border-slate-200 bg-white px-3 py-1">Backend: {API_BASE}</span>
                {lastRefresh && <span className="rounded-full border border-slate-200 bg-white px-3 py-1">Last refresh {lastRefresh}</span>}
                {latestUpdate && (
                  <span className="rounded-full border border-slate-200 bg-white px-3 py-1">
                    Latest event {new Date(latestUpdate).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
                  </span>
                )}
              </div>
            </div>

            <div className="grid min-w-60 grid-cols-2 gap-3">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Sessions</p>
                <p className="mt-3 text-3xl font-semibold">{sessions.length}</p>
              </div>
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                <p className="text-xs uppercase tracking-[0.24em] text-emerald-700">Healthy</p>
                <p className="mt-3 text-3xl font-semibold text-emerald-900">{healthyCount}</p>
              </div>
              <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4">
                <p className="text-xs uppercase tracking-[0.24em] text-rose-700">Anomalies</p>
                <p className="mt-3 text-3xl font-semibold text-rose-900">{anomalousCount}</p>
              </div>
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
                <p className="text-xs uppercase tracking-[0.24em] text-amber-800">Events</p>
                <p className="mt-3 text-3xl font-semibold text-amber-900">{totalEvents}</p>
              </div>
            </div>
          </div>
        </section>

        {error && (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-900 shadow-sm">
            {error}
          </div>
        )}

        <section className="flex flex-col gap-6">
          <div className="space-y-4 rounded-4xl border border-white/60 bg-white/75 p-5 shadow-[0_20px_60px_rgba(15,23,42,0.08)] backdrop-blur sm:p-6">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold">Live sessions</h2>
                <p className="mt-1 text-sm text-slate-500">Each card summarizes the current status, activity shape, and most recent action.</p>
              </div>
              <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                {sessions.length > 0 ? 'Active' : 'Waiting'}
              </span>
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              {loading && sessions.length === 0 && (
                <div className="col-span-full rounded-3xl border border-dashed border-slate-300 bg-slate-50/70 p-8 text-sm text-slate-500">
                  Loading session stream...
                </div>
              )}

              {!loading && sessions.length === 0 && (
                <div className="col-span-full rounded-3xl border border-dashed border-slate-300 bg-linear-to-br from-white to-slate-50 p-8 text-slate-600">
                  <h3 className="text-lg font-semibold text-slate-900">No sessions yet</h3>
                  <p className="mt-2 max-w-2xl text-sm leading-6">
                    Start the backend, run the simulator, and the dashboard will populate with real examples. The current simulator includes normal, looping, drifting, and failing sessions with duplicate and late-event chaos.
                  </p>
                  <div className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
                    <div className="rounded-2xl border border-slate-200 bg-white p-4 font-mono text-xs text-slate-700">
                      python simulator/cli.py --scenario normal
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-white p-4 font-mono text-xs text-slate-700">
                      python simulator/cli.py --scenario drift
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-white p-4 font-mono text-xs text-slate-700">
                      python simulator/cli.py --scenario loop
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-white p-4 font-mono text-xs text-slate-700">
                      python simulator/cli.py --scenario failure
                    </div>
                  </div>
                </div>
              )}

              {sessions.map((session) => {
                const meta = getStatusMeta(session.status)
                const success = session.success_events ?? 0
                const failures = session.failure_events ?? 0
                const total = session.total_events ?? 0
                const failureRatio = total > 0 ? Math.round((failures / total) * 100) : 0

                return (
                  <Link
                    key={session.session_id}
                    href={`/sessions/${session.session_id}`}
                    className={`group rounded-3xl border border-slate-200 bg-linear-to-br ${meta.accent} p-5 shadow-sm transition duration-200 hover:-translate-y-0.5 hover:shadow-lg`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                          <span>Session</span>
                          <span className="rounded-full bg-white/80 px-2 py-1 font-mono tracking-normal text-slate-700">{session.session_id}</span>
                        </div>
                        <div>
                          <h3 className="text-xl font-semibold text-slate-900">{meta.label}</h3>
                          <p className="mt-1 text-sm leading-6 text-slate-600">{meta.description}</p>
                        </div>
                      </div>
                      <span className={`shrink-0 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] ${meta.pill}`}>
                        {meta.label}
                      </span>
                    </div>

                    <div className="mt-5 grid grid-cols-2 gap-3 text-sm text-slate-600 sm:grid-cols-4">
                      <div className="rounded-2xl bg-white/75 p-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Events</p>
                        <p className="mt-2 text-lg font-semibold text-slate-900">{total}</p>
                      </div>
                      <div className="rounded-2xl bg-white/75 p-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Success</p>
                        <p className="mt-2 text-lg font-semibold text-slate-900">{success}</p>
                      </div>
                      <div className="rounded-2xl bg-white/75 p-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Failures</p>
                        <p className="mt-2 text-lg font-semibold text-slate-900">{failures}</p>
                      </div>
                      <div className="rounded-2xl bg-white/75 p-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Failure rate</p>
                        <p className="mt-2 text-lg font-semibold text-slate-900">{failureRatio}%</p>
                      </div>
                    </div>

                    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-600">
                      <span>Last action: {session.last_action ?? 'No action yet'}</span>
                      <span>Updated: {formatTime(session.updated_at)}</span>
                    </div>
                    {session.last_seen && (
                      <div className="mt-2 text-xs uppercase tracking-[0.24em] text-slate-500">
                        Last event observed {formatTime(session.last_seen)}
                      </div>
                    )}
                  </Link>
                )
              })}
            </div>
          </div>

          <div className="space-y-4 rounded-4xl border border-white/60 bg-white/75 p-5 shadow-[0_20px_60px_rgba(15,23,42,0.08)] backdrop-blur sm:p-6">
            <div>
              <h2 className="text-xl font-semibold">What to try</h2>
              <p className="mt-1 text-sm text-slate-500">
                Use the simulator scenarios to see different shapes of agent behavior and how the heuristics react.
              </p>
            </div>

            <div className="space-y-3 text-sm text-slate-700">
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex items-center justify-between gap-3">
                  <strong>Normal</strong>
                  <span className="rounded-full bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700">Healthy</span>
                </div>
                <p className="mt-2 text-slate-600">A straight line from read to write to verification, with an explicit completion step.</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex items-center justify-between gap-3">
                  <strong>Loop</strong>
                  <span className="rounded-full bg-rose-50 px-2 py-1 text-xs font-semibold text-rose-700">Looping</span>
                </div>
                <p className="mt-2 text-slate-600">Several command variants all fail in a similar shape, which should trip the fuzzy loop detector.</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex items-center justify-between gap-3">
                  <strong>Drift</strong>
                  <span className="rounded-full bg-sky-50 px-2 py-1 text-xs font-semibold text-sky-700">Drifting</span>
                </div>
                <p className="mt-2 text-slate-600">The main session starts in auth files, then slowly slides into CSS work while a shadow session stays focused.</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex items-center justify-between gap-3">
                  <strong>Failure</strong>
                  <span className="rounded-full bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-800">Failing</span>
                </div>
                <p className="mt-2 text-slate-600">A string of repeated failures shows how the system reacts when retries stop being productive.</p>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
