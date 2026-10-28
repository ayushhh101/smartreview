import { useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { useApi } from '../lib/useApi.js'
import { api } from '../lib/api.js'
import { pretty } from '../lib/format.js'
import { Stat, Loading, ErrorBlock, Empty, Card, Badge } from '../components/ui.jsx'

const kb = b => (b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${(b / 1024).toFixed(1)} KB`)
const sel = 'border border-slate-300 rounded px-2 py-1.5 text-sm bg-white'
const Btn = ({ children, ...p }) => <button {...p} className="bg-brand text-white text-sm rounded px-4 py-1.5 disabled:opacity-40">{children}</button>

export default function BDALab() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">BDA Lab</h1>
        <div className="mt-2 flex gap-2"><Badge>BDA</Badge><Badge>Educational simulations, real data</Badge></div>
      </div>
      <MapReduce />
      <div className="grid lg:grid-cols-2 gap-6"><Bloom /><Distinct /></div>
      <Benchmark />
      <Queries />
    </div>
  )
}

function useRunner() {
  const [res, setRes] = useState(null), [err, setErr] = useState(null), [busy, setBusy] = useState(false)
  const run = async (fn) => { setBusy(true); setErr(null); try { setRes(await fn()) } catch (e) { setErr(e); setRes(null) } finally { setBusy(false) } }
  return { res, err, busy, run }
}

function MapReduce() {
  const { data: jobs } = useApi('/bda/jobs')
  const [job, setJob] = useState('word_count'), [n, setN] = useState(10000), [m, setM] = useState(4), [r, setR] = useState(3)
  const { res, err, busy, run } = useRunner()
  const go = () => run(() => api(`/bda/mapreduce/${job}?n=${n}&mappers=${m}&reducers=${r}`, { method: 'POST' }))
  const t = res?.trace
  return (
    <Card title="MapReduce simulator" note="Educational MapReduce Simulation: one Python process, no cluster. Every phase is real code with a trace.">
      <div className="flex flex-wrap gap-3 items-end">
        <label className="text-sm">Job<select value={job} onChange={e => setJob(e.target.value)} className={`block mt-1 ${sel}`}>
          {(jobs?.jobs || []).map(j => <option key={j.id} value={j.id}>{j.title}</option>)}</select></label>
        <label className="text-sm">Reviews<select value={n} onChange={e => setN(+e.target.value)} className={`block mt-1 ${sel}`}>{[1000, 10000, 50000, 100000].map(v => <option key={v} value={v}>{v.toLocaleString()}</option>)}</select></label>
        <label className="text-sm">Mappers<select value={m} onChange={e => setM(+e.target.value)} className={`block mt-1 ${sel}`}>{[1, 2, 4, 8].map(v => <option key={v}>{v}</option>)}</select></label>
        <label className="text-sm">Reducers<select value={r} onChange={e => setR(+e.target.value)} className={`block mt-1 ${sel}`}>{[1, 2, 3, 6].map(v => <option key={v}>{v}</option>)}</select></label>
        <Btn onClick={go} disabled={busy}>{busy ? 'Running…' : 'Run job'}</Btn>
      </div>
      {jobs && <p className="text-xs text-ink-soft mt-2">{jobs.jobs.find(j => j.id === job)?.description}</p>}
      {err && <div className="mt-3"><ErrorBlock error={err} /></div>}
      {res && (
        <div className="mt-4 space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Phase title="1 Map" lines={[`${t.map.records_in.toLocaleString()} records in`, `${t.map.pairs_emitted.toLocaleString()} pairs out`, `${t.map.seconds}s`]} />
            <Phase title="2 Combine" lines={t.combine ? [`${t.combine.pairs_after.toLocaleString()} pairs left`, `${t.combine.reduction_pct}% less to shuffle`, `${t.combine.seconds}s`] : ['not used for this job']} />
            <Phase title="3 Shuffle" lines={[`${t.shuffle.keys.toLocaleString()} distinct keys`, `${t.config.reducers} partitions: ${t.shuffle.partitions.map(p => p.keys).join(' / ')} keys`, `${t.shuffle.seconds}s`]} />
            <Phase title="4 Reduce" lines={[`${t.reduce.keys_out.toLocaleString()} results`, `${t.reduce.seconds}s`]} />
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className={res.verified_against_naive ? 'text-pos font-medium' : 'text-neg font-medium'}>{res.verified_against_naive ? '✓ Result identical to a plain Python loop' : '✗ Result differs from the plain loop'}</span>
            <span className="text-ink-soft">MapReduce {res.mapreduce_seconds}s · plain loop {res.naive_seconds}s (one machine: the simulation has overhead; the model pays off when spread over many machines)</span>
          </div>
          <div className="grid lg:grid-cols-3 gap-4 text-sm">
            <div><div className="font-medium mb-1">Map output (first records)</div>{t.map.sample.map((s, i) => <div key={i} className="mb-2"><div className="text-ink-soft">{s.record}</div><div className="text-xs text-brand">{s.pairs.map(p => `(${p[0]}, ${JSON.stringify(p[1])})`).join('  ')}</div></div>)}</div>
            <div><div className="font-medium mb-1">Shuffle: grouped by key</div>{t.shuffle.sample.map((s, i) => <div key={i} className="mb-2"><b>{s.key}</b> <span className="text-ink-faint">{s.n_values} values</span><div className="text-xs text-ink-soft">[{s.values.map(v => JSON.stringify(v)).join(', ')}{s.n_values > 5 ? ', …' : ''}]</div></div>)}</div>
            <div><div className="font-medium mb-1">Top results ({res.n_keys.toLocaleString()} keys)</div>{res.top.slice(0, 10).map(x => <div key={x.key}>{x.key} <span className="text-ink-soft">{typeof x.value === 'object' ? `${x.value.avg} avg · ${x.value.reviews} reviews` : x.value.toLocaleString()}</span></div>)}</div>
          </div>
        </div>)}
    </Card>
  )
}
const Phase = ({ title, lines }) => <div className="border border-slate-200 rounded p-3"><div className="font-medium text-brand mb-1">{title}</div>{lines.map((l, i) => <div key={i} className="text-sm text-ink-soft">{l}</div>)}</div>

function Bloom() {
  const [rate, setRate] = useState(0.01)
  const { res, err, busy, run } = useRunner()
  return (
    <Card title="Bloom filter" note="Educational demo: have we seen this reviewer before? Tiny memory, no false negatives, a controllable false-positive rate.">
      <div className="flex gap-3 items-end">
        <label className="text-sm">Target false-positive rate<select value={rate} onChange={e => setRate(+e.target.value)} className={`block mt-1 ${sel}`}>{[0.05, 0.01, 0.001].map(v => <option key={v} value={v}>{v * 100}%</option>)}</select></label>
        <Btn onClick={() => run(() => api(`/bda/bloom?n=100000&error_rate=${rate}`))} disabled={busy}>{busy ? 'Running…' : 'Build + test'}</Btn>
      </div>
      {err && <div className="mt-3"><ErrorBlock error={err} /></div>}
      {res && <div className="mt-4 text-sm space-y-1.5">
        <div>{res.inserted.toLocaleString()} reviewer IDs inserted → {res.bits.toLocaleString()} bits ({kb(res.bytes)}), {res.hash_functions} hash functions, {Math.round(res.fill_ratio * 100)}% of bits set</div>
        <div className="text-pos">False negatives: {res.false_negatives} (a Bloom filter never forgets an inserted item)</div>
        <div>Unseen reviewers wrongly reported as present: {res.false_positives} of {res.probed_unseen.toLocaleString()} = <b>{(res.measured_fp_rate * 100).toFixed(2)}%</b> measured vs {(res.theoretical_fp_rate * 100).toFixed(2)}% theory</div>
        <div className="text-ink-soft">Memory: Bloom {kb(res.bytes)} vs about {kb(res.approx_python_set_bytes)} for a Python set (rough estimate)</div></div>}
    </Card>
  )
}

function Distinct() {
  const [field, setField] = useState('user_id')
  const { res, err, busy, run } = useRunner()
  return (
    <Card title="Distinct count (Flajolet-Martin)" note="Educational demo: estimate how many different values appear, using a sketch of a few hundred bytes.">
      <div className="flex gap-3 items-end">
        <label className="text-sm">Count distinct<select value={field} onChange={e => setField(e.target.value)} className={`block mt-1 ${sel}`}><option value="user_id">reviewers</option><option value="product_id">products</option></select></label>
        <Btn onClick={() => run(() => api(`/bda/distinct?field=${field}`))} disabled={busy}>{busy ? 'Running…' : 'Estimate'}</Btn>
      </div>
      {err && <div className="mt-3"><ErrorBlock error={err} /></div>}
      {res && <div className="mt-4 grid grid-cols-3 gap-3">
        <Stat label="Exact (set)" value={res.exact_distinct.toLocaleString()} /><Stat label="Estimate" value={res.estimated_distinct.toLocaleString()} />
        <Stat label="Error" value={`${res.error_pct > 0 ? '+' : ''}${res.error_pct}%`} hint={`${res.hash_functions} hash functions, ${res.sketch_bytes} bytes`} /></div>}
    </Card>
  )
}

function Benchmark() {
  const { data: d, error, loading } = useApi('/bda/benchmark')
  if (loading) return <Loading label="Loading benchmark" />
  if (error?.code === 'not_computed') return <Empty title="Benchmark not run yet"><pre className="bg-slate-50 rounded p-3 text-xs">python -m scripts.run_benchmark</pre></Empty>
  if (error) return <ErrorBlock error={error} />
  const wc = d.rows.filter(r => r.job === 'word_count').map(r => ({ n: r.n.toLocaleString(), 'Plain loop': r.naive_seconds, 'MapReduce simulation': r.mapreduce_seconds, 'MongoDB aggregation': r.mongo_seconds }))
  return (
    <Card title="Benchmark: three ways to run the same job" note={d.note}>
      <div className="h-60"><ResponsiveContainer><BarChart data={wc}><XAxis dataKey="n" label={{ value: 'Word count, reviews processed', position: 'insideBottom', offset: -2, fontSize: 11 }} /><YAxis unit="s" /><Tooltip /><Legend />
        <Bar dataKey="Plain loop" fill="#94A3B8" /><Bar dataKey="MapReduce simulation" fill="#2B4C9B" /><Bar dataKey="MongoDB aggregation" fill="#0F766E" /></BarChart></ResponsiveContainer></div>
      <div className="overflow-x-auto mt-3"><table className="w-full text-sm"><thead><tr className="text-left text-ink-soft border-b border-slate-200">{['Reviews', 'Job', 'Plain loop', 'MapReduce sim', 'MongoDB', 'Results match'].map(h => <th key={h} className="py-1.5 pr-3 font-medium">{h}</th>)}</tr></thead>
        <tbody>{d.rows.map((r, i) => <tr key={i} className="border-b border-slate-100"><td className="py-1.5 pr-3">{r.n.toLocaleString()}</td><td className="pr-3">{pretty(r.job)}</td><td className="pr-3">{r.naive_seconds}s</td><td className="pr-3">{r.mapreduce_seconds}s</td><td className="pr-3">{r.mongo_seconds}s</td><td className={r.results_match ? 'text-pos' : 'text-neg'}>{r.results_match ? 'yes' : 'NO'}</td></tr>)}</tbody></table></div>
    </Card>
  )
}

function Queries() {
  const { data: qs } = useApi('/bda/queries')
  const [id, setId] = useState(null)
  const { res, err, busy, run } = useRunner()
  const pick = q => { setId(q); run(() => api(`/bda/query/${q}`)) }
  return (
    <Card title="NoSQL queries (MongoDB aggregation pipelines)" note="Fixed server-side pipelines over the reviews collection; each shows the pipeline, timing and the access path MongoDB chose.">
      <div className="flex flex-wrap gap-2">{(qs?.queries || []).map(q => <button key={q.id} onClick={() => pick(q.id)} className={`text-xs rounded px-3 py-1.5 border ${id === q.id ? 'bg-brand text-white border-brand' : 'border-slate-300 bg-white'}`}>{q.title}</button>)}</div>
      {busy && <Loading label="Running query" />}
      {err && <div className="mt-3"><ErrorBlock error={err} /></div>}
      {res && <div className="mt-4 grid lg:grid-cols-2 gap-4">
        <div><div className="text-sm text-ink-soft mb-1">{res.description} · {res.seconds}s{res.plan ? ` · ${res.plan}` : ''}</div>
          <pre className="bg-slate-50 rounded p-3 text-xs overflow-x-auto">{JSON.stringify(res.pipeline, null, 2)}</pre></div>
        <div className="overflow-x-auto"><pre className="bg-slate-50 rounded p-3 text-xs">{res.rows.map(r => JSON.stringify(r)).join('\n')}</pre></div></div>}
    </Card>
  )
}
