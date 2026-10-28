import { useEffect, useRef, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { pretty, pct } from '../lib/format.js'
import { Stat, Card, Badge } from '../components/ui.jsx'

const sel = 'border border-slate-300 rounded px-2 py-1.5 text-sm bg-white'

export default function Streaming() {
  const [rate, setRate] = useState(20), [win, setWin] = useState(30), [burst, setBurst] = useState(true), [fast, setFast] = useState(false)
  const [running, setRunning] = useState(false), [snap, setSnap] = useState(null), [hist, setHist] = useState([]), [err, setErr] = useState(null)
  const es = useRef(null)
  const stop = () => { es.current?.close(); es.current = null; setRunning(false) }
  const start = () => {
    stop(); setSnap(null); setHist([]); setErr(null)
    const q = `rate=${rate}&window=${win}&interval=${fast ? 0.25 : 1}&seconds=600${burst ? '&burst_at=25&burst_len=12' : ''}`
    const s = new EventSource(`/api/bda/stream?${q}`)
    s.onmessage = e => { const d = JSON.parse(e.data); setSnap(d); setHist(h => [...h.slice(-89), { t: d.t, 'Negative %': Math.round(d.window.negative_share * 100), alert: !!d.alert }]) }
    s.onerror = () => { setErr('Stream connection lost. Is the backend running and MongoDB seeded?'); stop() }
    es.current = s; setRunning(true)
  }
  useEffect(() => () => es.current?.close(), [])
  const w = snap?.window
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Streaming</h1>
        <div className="mt-2 flex gap-2"><Badge>BDA</Badge><Badge>Simulated stream: replays real reviews as if live</Badge></div>
      </div>
      <Card title="Controls" note="Server-Sent Events push one snapshot per second. Sliding-window counters, reservoir sampling and a spike alert run on the server.">
        <div className="flex flex-wrap gap-4 items-end">
          <label className="text-sm">Reviews per second<select value={rate} onChange={e => setRate(+e.target.value)} className={`block mt-1 ${sel}`}>{[5, 20, 50, 100].map(v => <option key={v}>{v}</option>)}</select></label>
          <label className="text-sm">Window (seconds)<select value={win} onChange={e => setWin(+e.target.value)} className={`block mt-1 ${sel}`}>{[10, 30, 60, 120].map(v => <option key={v}>{v}</option>)}</select></label>
          <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={burst} onChange={e => setBurst(e.target.checked)} />Inject a negative burst at 25 s</label>
          <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={fast} onChange={e => setFast(e.target.checked)} />4x speed</label>
          {running ? <button onClick={stop} className="border border-slate-300 text-sm rounded px-4 py-1.5">Stop</button>
            : <button onClick={start} className="bg-brand text-white text-sm rounded px-4 py-1.5">Start stream</button>}
        </div>
        {err && <p className="mt-3 text-sm text-neg">{err}</p>}
      </Card>

      {snap && (<>
        {snap.alert && <div role="alert" className="border border-red-300 bg-red-50 text-neg rounded-lg px-4 py-3 text-sm font-medium">⚠ {snap.alert} ({pct(w.negative_share)} in the last {snap.window_seconds}s vs {pct(snap.baseline_negative_share)} normal)</div>}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Stat label="Simulated time" value={`${snap.t}s`} hint={`${snap.events_total.toLocaleString()} reviews so far`} />
          <Stat label={`Reviews in last ${snap.window_seconds}s`} value={w.events} hint={`${snap.new_events} this second`} />
          <Stat label="Window average rating" value={w.avg_rating ?? '–'} />
          <Stat label="Window negative share" value={pct(w.negative_share)} tone={snap.alert ? 'text-neg' : undefined} hint={`normal: ${pct(snap.baseline_negative_share)}`} />
        </div>
        <Card title="Negative share over time" note="Share of negative reviews inside the sliding window. The dashed line is the normal level; a burst pushes it above and triggers the alert.">
          <div className="h-56"><ResponsiveContainer><LineChart data={hist}><XAxis dataKey="t" unit="s" /><YAxis domain={[0, 100]} unit="%" /><Tooltip />
            <ReferenceLine y={Math.round(snap.baseline_negative_share * 100)} stroke="#94A3B8" strokeDasharray="4 4" />
            <Line dataKey="Negative %" stroke="#B42318" strokeWidth={2} dot={false} isAnimationActive={false} /></LineChart></ResponsiveContainer></div>
        </Card>
        <div className="grid lg:grid-cols-2 gap-6">
          <Card title="Aspects in the window" note="Mentions and how many are negative">
            {w.aspects.length === 0 ? <p className="text-sm text-ink-faint">No aspect mentions yet.</p> : w.aspects.map(a => (
              <div key={a.aspect} className="flex items-center gap-3 text-sm mb-1.5"><span className="w-36 capitalize">{pretty(a.aspect)}</span>
                <div className="flex-1 bg-slate-100 rounded h-3"><div className="bg-neg h-3 rounded" style={{ width: `${(100 * a.negative) / a.mentions}%` }} /></div>
                <span className="w-24 text-right text-ink-soft">{a.negative}/{a.mentions} negative</span></div>))}
          </Card>
          <Card title={`Reservoir sample (${snap.reservoir.length} of ${snap.reservoir_seen.toLocaleString()} seen)`} note="Algorithm R: every review so far has the same chance of being in this sample, using fixed memory">
            {snap.reservoir.map((r, i) => <div key={i} className="text-sm mb-1.5 border-b border-slate-100 pb-1.5"><span className="text-xs text-ink-faint">{'★'.repeat(r.rating)} </span><b>{r.title}</b> <span className="text-ink-soft">{r.text}</span></div>)}
          </Card>
        </div>
      </>)}
    </div>
  )
}
