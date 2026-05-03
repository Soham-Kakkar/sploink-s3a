"use client"

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'

interface Event {
  id: number
  timestamp: number
  step: number
  action: string
  input: string
  output: string
  status: string
  file_target: string | null
}

interface SessionData {
  session: {
    session_id: string
    status: string
    drift_streak?: number
  }
  summary: {
    total_events: number
    success_events: number
    failure_events: number
    action_distribution: Record<string, number>
    first_seen: number | null
    last_seen: number | null
    duration: number | null
  }
  detected_issues: string[]
  events: Event[]
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000'

const statusStyles: Record<string, { label: string; pill: string; panel: string; description: string }> = {
  healthy: {
    label: 'Healthy',
    pill: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    panel: 'from-emerald-50 to-lime-50',
    description: 'The session still looks aligned with its baseline work.',
  },
  looping: {
    label: 'Looping',
    pill: 'bg-rose-100 text-rose-800 border-rose-200',
    panel: 'from-rose-50 to-orange-50',
    description: 'The recent behavior is repeating with small variations.',
  },
  failing: {
    label: 'Failing',
    pill: 'bg-amber-100 text-amber-900 border-amber-200',
    panel: 'from-amber-50 to-yellow-50',
    description: 'The session is stuck in a back-to-back failure path.',
  },
  drifting: {
    label: 'Drifting',
    pill: 'bg-sky-100 text-sky-900 border-sky-200',
    panel: 'from-sky-50 to-cyan-50',
    description: 'The agent has moved away from the session baseline.',
  },
}

function formatTimestamp(value?: number | null) {
  if (value === null || value === undefined) return 'unknown'
  return new Date(value * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit' })
}

function formatDuration(value?: number | null) {
  if (value === null || value === undefined) return 'n/a'
  if (value < 60) return `${value.toFixed(1)}s`
  const minutes = Math.floor(value / 60)
  const seconds = Math.round(value % 60)
  return `${minutes}m ${seconds}s`
}

export default function SessionDetail() {
  const params = useParams();
  const { id } = params
  const [data, setData] = useState<SessionData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch(`${API_BASE}/sessions/${id}`, { cache: 'no-store' })
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`)
        }
        const json = await res.json()
        setData(json)
        setError(null)
      } catch (err) {
        console.error('Failed to fetch session detail', err)
        setError('Failed to load this session. Check that the backend is running and the session still exists.')
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [id])

  const meta = data ? statusStyles[data.session.status] ?? {
    label: data.session.status,
    pill: 'bg-slate-100 text-slate-700 border-slate-200',
    panel: 'from-slate-50 to-stone-50',
    description: 'No heuristic label is available for this session.',
  } : null

  if (loading && !data) {
    return <div className="min-h-screen px-6 py-10 text-slate-700">Loading session detail...</div>
  }

  return (
    <div className="min-h-screen px-4 py-6 text-slate-900 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <Link href="/" className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/80 px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
          <span aria-hidden="true">&larr;</span> Back to dashboard
        </Link>

        {error && (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-900 shadow-sm">
            {error}
          </div>
        )}

        {data && meta && (
          <>
            <section className={`rounded-4xl border border-white/60 bg-linear-to-br ${meta.panel} p-6 shadow-[0_20px_60px_rgba(15,23,42,0.08)] sm:p-8`}>
              <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
                <div className="max-w-3xl space-y-4">
                  <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                    <span className="rounded-full bg-white/80 px-3 py-1 font-mono tracking-normal text-slate-700">{data.session.session_id}</span>
                    <span>Session detail</span>
                  </div>
                  <div>
                    <h1 className="text-4xl font-semibold tracking-tight">{meta.label}</h1>
                    <p className="mt-3 max-w-2xl text-base leading-7 text-slate-600">{meta.description}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] ${meta.pill}`}>{meta.label}</span>
                    <span className="rounded-full border border-slate-200 bg-white/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-slate-600">
                      Drift streak {data.session.drift_streak ?? 0}
                    </span>
                    <span className="rounded-full border border-slate-200 bg-white/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-slate-600">
                      {data.summary.total_events} events observed
                    </span>
                  </div>
                </div>

                <div className="grid min-w-60 grid-cols-2 gap-3">
                  <div className="rounded-2xl border border-white/70 bg-white/80 p-4">
                    <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Total</p>
                    <p className="mt-3 text-3xl font-semibold">{data.summary.total_events}</p>
                  </div>
                  <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                    <p className="text-xs uppercase tracking-[0.24em] text-emerald-700">Success</p>
                    <p className="mt-3 text-3xl font-semibold text-emerald-900">{data.summary.success_events}</p>
                  </div>
                  <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4">
                    <p className="text-xs uppercase tracking-[0.24em] text-rose-700">Failure</p>
                    <p className="mt-3 text-3xl font-semibold text-rose-900">{data.summary.failure_events}</p>
                  </div>
                  <div className="rounded-2xl border border-sky-200 bg-sky-50 p-4">
                    <p className="text-xs uppercase tracking-[0.24em] text-sky-700">Duration</p>
                    <p className="mt-3 text-3xl font-semibold text-sky-900">{formatDuration(data.summary.duration)}</p>
                  </div>
                </div>
              </div>
            </section>

            <section className="space-y-4 rounded-4xl border border-white/60 bg-white/75 p-5 shadow-[0_20px_60px_rgba(15,23,42,0.08)] backdrop-blur sm:p-6">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h2 className="text-xl font-semibold">Detected issues</h2>
                    <p className="mt-1 text-sm text-slate-500">The system turns session state into plain-language notes so it is easier to debug quickly.</p>
                  </div>
                </div>

                <div className="space-y-3">
                  {data.detected_issues.map((issue) => (
                    <div key={issue} className="rounded-2xl border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-700 shadow-sm">
                      {issue}
                    </div>
                  ))}
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <p className="text-xs uppercase tracking-[0.24em] text-slate-400">First seen</p>
                    <p className="mt-2 text-sm font-medium text-slate-900">{formatTimestamp(data.summary.first_seen)}</p>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Last seen</p>
                    <p className="mt-2 text-sm font-medium text-slate-900">{formatTimestamp(data.summary.last_seen)}</p>
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Action distribution</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {Object.entries(data.summary.action_distribution).map(([action, count]) => (
                      <span key={action} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
                        {action}: {count}
                      </span>
                    ))}
                  </div>
                </div>
            </section>

            <section className="space-y-4 rounded-4xl border border-white/60 bg-white/75 p-5 shadow-[0_20px_60px_rgba(15,23,42,0.08)] backdrop-blur sm:p-6">
              <div>
                <h2 className="text-xl font-semibold">Event timeline</h2>
                <p className="mt-1 text-sm text-slate-500">Each card shows what the agent tried, what came back, and whether the event looks healthy or anomalous.</p>
              </div>

              <div className="space-y-4">
                {data.events.map((event, index) => {
                  const isFailure = event.status === 'failure'
                  const hasMetadata = Boolean(event.file_target)
                  const borderClass = isFailure ? 'border-rose-200 bg-rose-50/70' : hasMetadata ? 'border-slate-200 bg-white' : 'border-amber-200 bg-amber-50/70'

                  return (
                    <article key={event.id} className={`rounded-3xl border p-5 shadow-sm ${borderClass}`}>
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div className="space-y-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-white">Step {event.step}</span>
                            <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-slate-700">{event.action}</span>
                            <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] ${isFailure ? 'bg-rose-100 text-rose-700' : 'bg-emerald-100 text-emerald-700'}`}>
                              {event.status}
                            </span>
                            {!hasMetadata && (
                              <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-amber-800">
                                Incomplete data
                              </span>
                            )}
                          </div>
                          <div>
                            <h3 className="text-lg font-semibold text-slate-900">Event {index + 1}</h3>
                            <p className="mt-1 text-sm text-slate-500">{formatTimestamp(event.timestamp)}</p>
                          </div>
                        </div>
                        <div className="text-sm text-slate-500">
                          {hasMetadata ? (
                            <span className="rounded-full border border-slate-200 bg-white px-3 py-1">File: {event.file_target}</span>
                          ) : (
                            <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-800">No file target supplied</span>
                          )}
                        </div>
                      </div>

                      <div className="mt-5 grid gap-4 lg:grid-cols-2">
                        <div className="rounded-2xl border border-slate-200 bg-white p-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Input</p>
                          <pre className="mt-3 whitespace-pre-wrap wrap-break-word text-sm leading-6 text-slate-900">{event.input || 'No input supplied'}</pre>
                        </div>
                        <div className="rounded-2xl border border-slate-200 bg-white p-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Output</p>
                          <pre className="mt-3 whitespace-pre-wrap wrap-break-word text-sm leading-6 text-slate-900">{event.output || 'No output supplied'}</pre>
                        </div>
                      </div>
                    </article>
                  )
                })}
                {data.events.length === 0 && (
                  <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50/70 p-8 text-sm text-slate-500">
                    No events were recorded for this session yet.
                  </div>
                )}
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  )
}
