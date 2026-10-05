import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ComposedChart, Bar, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { useApi } from '../lib/useApi.js'
import { pretty, pct, healthTone, TREND } from '../lib/format.js'
import { Stat, Loading, ErrorBlock, Card } from '../components/ui.jsx'

export default function ProductDetail() {
  const { id } = useParams()
  const { data: d, error, loading } = useApi(`/products/${encodeURIComponent(id)}`)
  return (
    <div className="space-y-6">
      <Link to="/products" className="text-sm text-brand hover:underline">← All products</Link>
      {loading && <Loading label="Loading product" />}
      {error && <ErrorBlock error={error} />}
      {d && <Body d={d} />}
    </div>
  )
}

function Body({ d }) {
  const t = d.trend, h = d.health, c = h.components
  const [sel, setSel] = useState(d.weakest_aspect?.aspect || null)
  const [sent, setSent] = useState('negative')
  const aspects = Object.entries(d.aspects).sort((a, b) => b[1].mentions - a[1].mentions)
  const series = t.series.map(s => ({ ...s, 'Positive %': Math.round(s.positive_ratio * 100) }))
  const hist = Object.entries(d.rating_histogram)
  const hmax = Math.max(...hist.map(([, v]) => v), 1)

  return (
    <>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{d.name || d.product_id}</h1>
        <div className="text-xs text-ink-faint mt-1">{d.product_id} · reviews from {d.first_review.slice(0, 10)} to {d.last_review.slice(0, 10)}</div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Health score" value={h.score} tone={healthTone(h.score)} hint="Heuristic, 0–100" />
        <Stat label="Reviews" value={d.n_reviews.toLocaleString()} />
        <Stat label="Average rating" value={d.avg_rating.toFixed(2)} />
        <Stat label="Positive reviews" value={pct(d.positive_ratio)} hint={`Negative: ${pct(d.negative_ratio)}`} />
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <Card title="How the score is built" note={h.label}>
          <table className="text-sm w-full">
            <tbody>
              <Row k="Aspect positivity (×0.40)" v={c.aspect_mean_positive_ratio == null ? 'not enough aspect mentions: dropped, weights renormalised' : `${pct(c.aspect_mean_positive_ratio)} across ${c.aspects_used} aspects`} />
              <Row k="Positive reviews (×0.30)" v={pct(c.overall_positive_ratio)} />
              <Row k="Rating, scaled 0–1 (×0.30)" v={c.rating_component.toFixed(2)} />
              <Row k="Trend penalty (max 10)" v={h.penalty ? `−${h.penalty}` : 'none'} />
            </tbody>
          </table>
          <div className="mt-3 flex items-center gap-2 text-sm">
            <span className={`text-xs rounded px-2 py-0.5 ${TREND[t.status].cls}`}>{TREND[t.status].label}</span>
            {t.status !== 'insufficient_data'
              ? <span className="text-ink-soft">Positive share: {pct(t.prior.positive_ratio)} → {pct(t.recent.positive_ratio)} (previous vs latest 12 months, n={t.prior.n}/{t.recent.n})</span>
              : <span className="text-ink-faint">Needs 15+ reviews in each of the last two 12-month windows.</span>}
          </div>
        </Card>

        <Card title="Rating distribution">
          <div className="space-y-1.5">
            {hist.reverse().map(([star, n]) => (
              <div key={star} className="flex items-center gap-3 text-sm">
                <span className="w-10 text-ink-soft">{star} ★</span>
                <div className="flex-1 bg-slate-100 rounded h-3"><div className="bg-brand h-3 rounded" style={{ width: `${(100 * n) / hmax}%` }} /></div>
                <span className="w-12 text-right text-ink-soft">{n}</span>
              </div>))}
          </div>
        </Card>
      </div>

      <Card title="Aspect sentiment" note="Share of mentions that are positive / neutral / negative. Click an aspect to read the reviews behind it.">
        {aspects.length === 0 ? <p className="text-sm text-ink-faint">No aspect mentions found in these reviews.</p> : (
          <div className="space-y-1">
            {aspects.map(([a, v]) => (
              <button key={a} onClick={() => setSel(a)} aria-pressed={sel === a}
                className={`w-full flex items-center gap-3 text-sm text-left rounded px-2 py-1.5 ${sel === a ? 'bg-slate-100' : 'hover:bg-slate-50'}`}>
                <span className="w-40 capitalize">{pretty(a)}</span>
                <div className="flex-1 flex h-3 rounded overflow-hidden bg-slate-100" title={`${v.positive} positive · ${v.neutral} neutral · ${v.negative} negative`}>
                  <div className="bg-pos" style={{ width: `${(100 * v.positive) / v.mentions}%` }} />
                  <div className="bg-neu" style={{ width: `${(100 * v.neutral) / v.mentions}%` }} />
                  <div className="bg-neg" style={{ width: `${(100 * v.negative) / v.mentions}%` }} />
                </div>
                <span className="w-28 text-right text-ink-soft">{pct(v.positive_ratio)} of {v.mentions}</span>
              </button>))}
          </div>)}
        {sel && (
          <div className="mt-5 border-t border-slate-100 pt-4">
            <div className="flex items-center gap-3 mb-2">
              <div className="font-medium capitalize">{pretty(sel)}: reviews</div>
              {['negative', 'neutral', 'positive'].map(s => (
                <button key={s} onClick={() => setSent(s)} className={`text-xs rounded px-2 py-1 border ${sent === s ? 'bg-brand text-white border-brand' : 'border-slate-300'}`}>{s}</button>))}
            </div>
            <Evidence id={d.product_id} aspect={sel} sentiment={sent} />
          </div>)}
      </Card>

      <Card title="Reviews over time" note={`By ${t.granularity}. Bars = review count, line = % positive. Few reviews in a period make the line noisy.`}>
        <div className="h-64"><ResponsiveContainer>
          <ComposedChart data={series}>
            <XAxis dataKey="period" tick={{ fontSize: 11 }} /><YAxis yAxisId="n" allowDecimals={false} />
            <YAxis yAxisId="p" orientation="right" domain={[0, 100]} /><Tooltip /><Legend />
            <Bar yAxisId="n" dataKey="n" name="Reviews" fill="#CBD5E1" />
            <Line yAxisId="p" dataKey="Positive %" stroke="#0F766E" strokeWidth={2} dot={false} />
          </ComposedChart>
        </ResponsiveContainer></div>
      </Card>
      <p className="text-xs text-ink-faint">{d.note}</p>
    </>
  )
}

const Row = ({ k, v }) => <tr className="border-b border-slate-100"><td className="py-1.5 pr-4 text-ink-soft">{k}</td><td className="py-1.5">{v}</td></tr>

function Evidence({ id, aspect, sentiment }) {
  const { data, error, loading } = useApi(`/products/${encodeURIComponent(id)}/evidence?aspect=${aspect}&sentiment=${sentiment}&limit=5`)
  if (loading) return <Loading label="Loading reviews" />
  if (error) return <ErrorBlock error={error} />
  if (!data.reviews.length) return <p className="text-sm text-ink-faint">No {sentiment} reviews mention this aspect.</p>
  return (
    <ul className="space-y-3">{data.reviews.map((r, i) => (
      <li key={i} className="text-sm border border-slate-200 rounded p-3">
        <div className="flex justify-between text-xs text-ink-faint"><span>{'★'.repeat(r.rating)}{'☆'.repeat(5 - r.rating)} · {r.review_date.slice(0, 10)}</span><span>{r.helpful_votes} helpful</span></div>
        {r.title && <div className="font-medium mt-1">{r.title}</div>}
        <p className="text-ink-soft mt-1">{r.text}</p>
      </li>))}</ul>
  )
}
