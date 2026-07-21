import React, { useEffect, useMemo, useState } from 'react'
import { fetchAlerts, fetchSummary, sendChat, triggerSpike } from './api'

function formatCurrency(value) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 4,
  }).format(value || 0)
}

function formatNumber(value) {
  return new Intl.NumberFormat('en-US').format(value || 0)
}

function trendGlyph(trend) {
  if (trend === 'up') return '^'
  if (trend === 'down') return 'v'
  return '-'
}

function statusTone(status) {
  return status === 'anomaly'
    ? 'border-ember-500/40 bg-ember-500/10 text-ember-300'
    : 'border-sea-500/30 bg-sea-500/10 text-sea-300'
}

function Sparkline({ points = [], alert = false }) {
  if (!points.length) {
    return <div className="h-24 rounded-2xl border border-white/10 bg-white/[0.03]" />
  }

  const width = 240
  const height = 96
  const pad = 10
  const min = Math.min(...points)
  const max = Math.max(...points)
  const range = Math.max(1e-6, max - min)
  const step = points.length === 1 ? 0 : (width - pad * 2) / (points.length - 1)
  const coords = points.map((value, index) => {
    const x = pad + index * step
    const y = height - pad - ((value - min) / range) * (height - pad * 2)
    return `${x},${y}`
  }).join(' ')

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-24 w-full overflow-visible rounded-2xl border border-white/10 bg-white/[0.03]">
      <defs>
        <linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={alert ? '#fb7185' : '#34d399'} stopOpacity="0.45" />
          <stop offset="100%" stopColor={alert ? '#fb7185' : '#34d399'} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <polyline points={coords} fill="none" stroke={alert ? '#fb7185' : '#5eead4'} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <polygon points={`${pad},${height - pad} ${coords} ${width - pad},${height - pad}`} fill="url(#sparkFill)" />
    </svg>
  )
}

function TimelineChart({ points = [], selected = null }) {
  const series = useMemo(() => points.map((point) => point.cost_usd), [points])

  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-5 shadow-glow">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-sm uppercase tracking-[0.3em] text-slate-400">Cost Over Time</div>
          <div className="text-lg font-semibold text-white">{selected ? selected.customer_label : 'All customers'}</div>
        </div>
        <div className="text-xs text-slate-400">bucketed from live trace spans</div>
      </div>
      <Sparkline points={series.length ? series : []} alert={selected?.status === 'anomaly'} />
    </div>
  )
}

function IncidentList({ incidents, onSelect, activeId }) {
  return (
    <div className="space-y-3">
      {incidents.length === 0 ? (
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 text-sm text-slate-400">No incidents yet. Trigger a spike to generate one.</div>
      ) : incidents.map((incident) => (
        <button
          key={incident.trace_ids[0] || incident.generated_at}
          onClick={() => onSelect(incident)}
          className={`w-full rounded-2xl border p-4 text-left transition ${activeId === (incident.trace_ids[0] || incident.generated_at) ? 'border-cyan-400/60 bg-cyan-400/10' : 'border-white/10 bg-white/[0.03] hover:bg-white/[0.05]'}`}
        >
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="font-medium text-white">{incident.reason}</div>
              <div className="mt-1 text-xs text-slate-400">
                {incident.customer_id} · {incident.anomaly_ratio.toFixed(2)}x baseline · {formatCurrency(incident.current_cost_usd)}
              </div>
            </div>
            <div className="text-right text-xs text-slate-500">{new Date(incident.generated_at).toLocaleTimeString()}</div>
          </div>
        </button>
      ))}
    </div>
  )
}

function DetailPane({ selectedCustomer, incident, onTriggerSpike, spikeBusy }) {
  return (
    <div className="space-y-4 rounded-3xl border border-white/10 bg-white/[0.04] p-5 shadow-glow">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm uppercase tracking-[0.3em] text-slate-400">Incident</div>
          <div className="text-xl font-semibold text-white">{selectedCustomer?.customer_label || 'Select a customer'}</div>
        </div>
        <button
          onClick={() => onTriggerSpike(selectedCustomer?.customer_id)}
          disabled={!selectedCustomer || spikeBusy}
          className="rounded-xl border border-emerald-400/40 bg-emerald-400/10 px-4 py-2 text-sm font-medium text-emerald-200 transition hover:bg-emerald-400/20 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {spikeBusy ? 'Triggering...' : 'Trigger Spike'}
        </button>
      </div>

      {incident ? (
        <div className="space-y-4">
          <div className={`rounded-2xl border p-4 ${statusTone('anomaly')}`}>
            <div className="font-medium text-white">{incident.reason}</div>
            <div className="mt-2 grid grid-cols-2 gap-3 text-sm text-slate-200 sm:grid-cols-4">
              <div>
                <div className="text-slate-400">Current Cost</div>
                <div>{formatCurrency(incident.current_cost_usd)}</div>
              </div>
              <div>
                <div className="text-slate-400">Baseline</div>
                <div>{formatCurrency(incident.baseline_cost_usd)}</div>
              </div>
              <div>
                <div className="text-slate-400">Calls</div>
                <div>{incident.current_call_count}</div>
              </div>
              <div>
                <div className="text-slate-400">Ratio</div>
                <div>{incident.anomaly_ratio.toFixed(2)}x</div>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-slate-950/50 p-4">
            <div className="mb-3 text-sm font-medium text-slate-300">Trace Evidence</div>
            <div className="space-y-3">
              {incident.evidence.map((span) => (
                <div key={span.span_id || `${span.name}-${span.timestamp_ms}`} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-medium text-white">{span.name}</div>
                    <div className="text-xs text-slate-400">{span.call_type}</div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-400">
                    <span>model: {span.model}</span>
                    <span>cost: {formatCurrency(span.cost_usd)}</span>
                    <span>input: {formatNumber(span.input_tokens)}</span>
                    <span>output: {formatNumber(span.output_tokens)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-white/10 p-8 text-sm text-slate-400">
          Select an incident to inspect the trace details and root cause.
        </div>
      )}
    </div>
  )
}

export default function App() {
  const [summary, setSummary] = useState(null)
  const [selectedCustomerId, setSelectedCustomerId] = useState('')
  const [selectedIncident, setSelectedIncident] = useState(null)
  const [alertsByCustomer, setAlertsByCustomer] = useState({})
  const [chatCustomerId, setChatCustomerId] = useState('')
  const [chatMessage, setChatMessage] = useState('Please review my AI usage spike and summarize what happened.')
  const [chatResponse, setChatResponse] = useState(null)
  const [chatBusy, setChatBusy] = useState(false)
  const [loadingSummary, setLoadingSummary] = useState(true)
  const [loadingAlerts, setLoadingAlerts] = useState(false)
  const [error, setError] = useState('')
  const [sigNozReady, setSigNozReady] = useState(false)
  const [sigNozStatusText, setSigNozStatusText] = useState('Waiting for trace data')
  const [spikeBusy, setSpikeBusy] = useState(false)
  const [windows, setWindows] = useState({ current_window_minutes: 15, baseline_window_minutes: 60 })

  const customers = summary?.customers || []
  const selectedCustomer = useMemo(
    () => customers.find((customer) => customer.customer_id === selectedCustomerId) || null,
    [customers, selectedCustomerId],
  )
  const selectedCustomerSeries = selectedCustomer?.cost_time_series || []

  async function loadSummary() {
    setError('')
    setLoadingSummary(true)
    try {
      const data = await fetchSummary(windows)
      setSummary(data)
      setSigNozReady(true)
      setSigNozStatusText(`Live trace data available from ${data.source}`)
      if (data.customers?.length && !chatCustomerId) {
        setChatCustomerId(data.customers[0].customer_id)
      }
      if (data.customers?.length && !data.customers.some((c) => c.customer_id === selectedCustomerId)) {
        setSelectedCustomerId(data.customers[0].customer_id)
      }
      if (!data.customers?.length) {
        setSelectedCustomerId('')
        setSelectedIncident(null)
      }
    } catch (err) {
      setError(err.message || 'Unable to load summary')
      setSigNozReady(false)
      setSigNozStatusText(err.message || 'SigNoz not reachable')
    } finally {
      setLoadingSummary(false)
    }
  }

  async function loadAlerts(customerId) {
    if (!customerId) return
    setError('')
    setLoadingAlerts(true)
    try {
      const data = await fetchAlerts(customerId, windows)
      setAlertsByCustomer((prev) => ({ ...prev, [customerId]: data }))
      const firstIncident = data.alerts?.[0] || null
      setSelectedIncident(firstIncident)
    } catch (err) {
      setError(err.message || 'Unable to load alerts')
    } finally {
      setLoadingAlerts(false)
    }
  }

  useEffect(() => {
    loadSummary()
    const timer = setInterval(loadSummary, 8000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    if (selectedCustomerId) {
      loadAlerts(selectedCustomerId)
    }
  }, [selectedCustomerId, windows.current_window_minutes, windows.baseline_window_minutes])

  useEffect(() => {
    if (selectedCustomerId && !chatCustomerId) {
      setChatCustomerId(selectedCustomerId)
    }
  }, [selectedCustomerId, chatCustomerId])

  const activeAlerts = alertsByCustomer[selectedCustomerId]?.alerts || []
  const incidentCount = customers.filter((customer) => customer.status === 'anomaly').length

  async function handleTriggerSpike(customerId) {
    if (!customerId) return
    setSpikeBusy(true)
    setError('')
    try {
      await triggerSpike(customerId, 6, 4)
      await loadSummary()
      await loadAlerts(customerId)
    } catch (err) {
      setError(err.message || 'Unable to trigger spike')
    } finally {
      setSpikeBusy(false)
    }
  }

  async function handleSendChat(event) {
    event.preventDefault()
    if (!chatCustomerId.trim() || !chatMessage.trim()) return
    setChatBusy(true)
    setError('')
    try {
      const response = await sendChat(chatCustomerId.trim(), chatMessage.trim())
      setChatResponse(response)
      setSelectedCustomerId(response.customer_id)
      await loadSummary()
      await loadAlerts(response.customer_id)
    } catch (err) {
      setError(err.message || 'Unable to send chat')
    } finally {
      setChatBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-[radial-grid] bg-[length:24px_24px] text-slate-100">
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top_left,_rgba(45,212,191,0.15),_transparent_35%),radial-gradient(circle_at_bottom_right,_rgba(249,115,22,0.12),_transparent_30%),linear-gradient(180deg,#07111f_0%,#040814_100%)]" />
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <header className="mb-8 rounded-[2rem] border border-white/10 bg-white/[0.04] p-6 shadow-glow backdrop-blur">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-400/10 px-3 py-1 text-xs uppercase tracking-[0.3em] text-cyan-200">
                  Per-Customer AI Cost Radar
                </div>
                <div
                  className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium uppercase tracking-[0.25em] ${
                    sigNozReady
                      ? 'border-sea-400/40 bg-sea-400/10 text-sea-200'
                      : 'border-slate-500/40 bg-slate-500/10 text-slate-300'
                  }`}
                >
                  <span className={`h-2 w-2 rounded-full ${sigNozReady ? 'bg-sea-300 animate-pulseGlow' : 'bg-slate-400'}`} />
                  {sigNozReady ? 'SigNoz Ready' : 'SigNoz Not Ready'}
                </div>
              </div>
              <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-5xl">
                Watch one customer spend spike ripple through the live trace graph.
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-6 text-slate-300 sm:text-base">
                Live backend traces, customer-specific anomaly detection, and a single-click spike trigger for demo day.
              </p>
              <p className="mt-3 text-xs uppercase tracking-[0.3em] text-slate-500">
                {sigNozStatusText}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:min-w-[420px]">
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Customers</div>
                <div className="mt-2 text-2xl font-semibold text-white">{formatNumber(customers.length)}</div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Incidents</div>
                <div className="mt-2 text-2xl font-semibold text-white">{formatNumber(incidentCount)}</div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Window</div>
                <div className="mt-2 text-2xl font-semibold text-white">{windows.current_window_minutes}m</div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Status</div>
                <div className="mt-2 text-2xl font-semibold text-white">{loadingSummary ? 'Loading' : 'Live'}</div>
              </div>
            </div>
          </div>
          <div className="mt-6 flex flex-wrap items-center gap-3 text-sm text-slate-300">
            <button
              onClick={loadSummary}
              className="rounded-xl border border-white/10 bg-white/5 px-4 py-2 transition hover:bg-white/10"
            >
              Refresh now
            </button>
            <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-2">
              <span className="text-slate-400">Current</span>
              <input
                type="number"
                min="1"
                max="120"
                value={windows.current_window_minutes}
                onChange={(e) => setWindows((w) => ({ ...w, current_window_minutes: Number(e.target.value || 1) }))}
                className="w-16 bg-transparent text-white outline-none"
              />
              <span className="text-slate-400">min</span>
            </label>
            <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-2">
              <span className="text-slate-400">Baseline</span>
              <input
                type="number"
                min="5"
                max="240"
                value={windows.baseline_window_minutes}
                onChange={(e) => setWindows((w) => ({ ...w, baseline_window_minutes: Number(e.target.value || 5) }))}
                className="w-16 bg-transparent text-white outline-none"
              />
              <span className="text-slate-400">min</span>
            </label>
            {error ? <span className="text-ember-300">{error}</span> : <span className="text-slate-500">{loadingAlerts ? 'Loading customer details...' : 'Auto-refresh every 8 seconds'}</span>}
          </div>
        </header>

        <section className="mb-6 rounded-[2rem] border border-white/10 bg-white/[0.04] p-6 shadow-glow">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm uppercase tracking-[0.3em] text-slate-400">Live Customer Source</div>
              <div className="text-lg font-semibold text-white">Send a real request for a real customer_id</div>
            </div>
            <div className="text-xs text-slate-500">This input decides which tenant appears in SigNoz</div>
          </div>
          <form onSubmit={handleSendChat} className="grid gap-3 lg:grid-cols-[220px_1fr_auto]">
            <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-3">
              <span className="text-slate-400">Customer</span>
              <input
                type="text"
                value={chatCustomerId}
                onChange={(e) => setChatCustomerId(e.target.value)}
                placeholder="cust_001"
                className="flex-1 bg-transparent text-white outline-none"
              />
            </label>
            <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-3">
              <span className="text-slate-400">Message</span>
              <input
                type="text"
                value={chatMessage}
                onChange={(e) => setChatMessage(e.target.value)}
                placeholder="Ask your AI assistant anything..."
                className="flex-1 bg-transparent text-white outline-none"
              />
            </label>
            <button
              type="submit"
              disabled={chatBusy}
              className="rounded-xl border border-cyan-400/40 bg-cyan-400/10 px-5 py-3 font-medium text-cyan-200 transition hover:bg-cyan-400/20 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {chatBusy ? 'Sending...' : 'Send Live Chat'}
            </button>
          </form>
          <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-500">
            <span>customer_id comes from this form, not a hardcoded list</span>
            <span>LLM/tool spans are traced in SigNoz</span>
            <span>spike trigger stays separate for demo control</span>
          </div>
          {chatResponse ? (
            <div className="mt-4 rounded-2xl border border-sea-400/20 bg-sea-400/5 p-4 text-sm text-slate-200">
              <div className="font-medium text-white">Last request</div>
              <div className="mt-1 text-slate-400">
                scenario: {chatResponse.scenario} · cost: {formatCurrency(chatResponse.total_cost_usd)} · tokens: {formatNumber(chatResponse.total_input_tokens)} in / {formatNumber(chatResponse.total_output_tokens)} out
              </div>
              <div className="mt-1 text-slate-400">
                assistant: {chatResponse.assistant_message}
              </div>
            </div>
          ) : null}
        </section>

        <main className="grid gap-6 lg:grid-cols-[1.35fr_0.95fr]">
          <section className="space-y-6">
            <div className="overflow-hidden rounded-[2rem] border border-white/10 bg-white/[0.04] shadow-glow">
              <div className="border-b border-white/10 px-6 py-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm uppercase tracking-[0.3em] text-slate-400">Customers</div>
                    <div className="text-lg font-semibold text-white">Spend radar overview</div>
                  </div>
                  <div className="text-xs text-slate-400">click a customer to inspect the trace</div>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-white/10">
                  <thead className="bg-white/[0.02] text-left text-xs uppercase tracking-[0.2em] text-slate-400">
                    <tr>
                      <th className="px-6 py-3">Customer</th>
                      <th className="px-6 py-3">Current Cost</th>
                      <th className="px-6 py-3">Calls</th>
                      <th className="px-6 py-3">Trend</th>
                      <th className="px-6 py-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/10">
                    {customers.length ? customers.map((customer) => (
                      <tr
                        key={customer.customer_id}
                        onClick={() => setSelectedCustomerId(customer.customer_id)}
                        className={`cursor-pointer transition hover:bg-white/[0.04] ${selectedCustomerId === customer.customer_id ? 'bg-cyan-400/10' : ''}`}
                      >
                        <td className="px-6 py-4">
                          <div className="font-medium text-white">{customer.customer_label}</div>
                          <div className="text-xs text-slate-400">{customer.customer_id}</div>
                        </td>
                        <td className="px-6 py-4 text-slate-200">{formatCurrency(customer.current_cost_usd)}</td>
                        <td className="px-6 py-4 text-slate-200">{formatNumber(customer.current_call_count)}</td>
                        <td className="px-6 py-4 text-slate-200">
                          <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs">
                            {trendGlyph(customer.trend)} {customer.trend}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${statusTone(customer.status)}`}>
                            {customer.status}
                          </span>
                        </td>
                      </tr>
                    )) : (
                      <tr>
                        <td colSpan="5" className="px-6 py-10 text-center text-sm text-slate-400">
                          No live customer traces yet. Send a real `/chat` request or trigger a spike to create original data.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <TimelineChart points={selectedCustomerSeries} selected={selectedCustomer} />
          </section>

          <aside className="space-y-6">
            <DetailPane
              selectedCustomer={selectedCustomer}
              incident={selectedIncident}
              onTriggerSpike={handleTriggerSpike}
              spikeBusy={spikeBusy}
            />

            <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-5 shadow-glow">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-sm uppercase tracking-[0.3em] text-slate-400">Incidents</div>
                  <div className="text-lg font-semibold text-white">Flagged alerts</div>
                </div>
                <div className="text-xs text-slate-500">for {selectedCustomerId}</div>
              </div>
              <IncidentList
                incidents={activeAlerts}
                onSelect={setSelectedIncident}
                activeId={selectedIncident?.trace_ids?.[0] || selectedIncident?.generated_at || null}
              />
            </div>
          </aside>
        </main>
      </div>
    </div>
  )
}
