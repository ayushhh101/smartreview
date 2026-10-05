import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../lib/useApi.js'
import { pretty, pct, healthTone, TREND } from '../lib/format.js'
import { Loading, ErrorBlock, Empty, Badge } from '../components/ui.jsx'

const PAGE = 25

export default function Products() {
  const [q, setQ] = useState('')
  const [dq, setDq] = useState('')
  const [sort, setSort] = useState('health_desc')
  const [min, setMin] = useState(20)
  const [offset, setOffset] = useState(0)
  useEffect(() => { const t = setTimeout(() => { setDq(q); setOffset(0) }, 300); return () => clearTimeout(t) }, [q])
  const path = `/products?q=${encodeURIComponent(dq)}&sort=${sort}&min_reviews=${min}&limit=${PAGE}&offset=${offset}`
  const { data, error, loading } = useApi(path)

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Products</h1>
        <div className="mt-2 flex gap-2"><Badge>BDA + NLP</Badge><Badge>Phase 4</Badge></div>
      </div>

      <div className="flex flex-wrap gap-3 items-end">
        <label className="text-sm">Search<input value={q} onChange={e => setQ(e.target.value)} placeholder="Product name or ID"
          className="block border border-slate-300 rounded px-2 py-1.5 w-64 mt-1" /></label>
        <label className="text-sm">Sort<select value={sort} onChange={e => { setSort(e.target.value); setOffset(0) }}
          className="block border border-slate-300 rounded px-2 py-1.5 mt-1">
          <option value="health_desc">Health: best first</option><option value="health_asc">Health: worst first</option>
          <option value="reviews_desc">Most reviews</option><option value="rating_desc">Rating: high to low</option>
          <option value="rating_asc">Rating: low to high</option></select></label>
        <label className="text-sm">Min reviews<select value={min} onChange={e => { setMin(+e.target.value); setOffset(0) }}
          className="block border border-slate-300 rounded px-2 py-1.5 mt-1">
          {[5, 10, 20, 50, 100].map(n => <option key={n} value={n}>{n}+</option>)}</select></label>
      </div>

      {loading && <Loading label="Loading products" />}
      {error?.code === 'not_computed' && (
        <Empty title="Analytics not computed yet">
          <p>Build the per-product health scores from the reviews in MongoDB:</p>
          <pre className="bg-slate-50 rounded p-3 text-xs">python -m scripts.compute_analytics</pre>
        </Empty>)}
      {error && error.code !== 'not_computed' && <ErrorBlock error={error} />}

      {data && data.items.length === 0 && (
        <Empty title="No products match">Try a lower minimum review count or a different search.</Empty>)}
      {data && data.items.length > 0 && (
        <>
          <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-ink-soft border-b border-slate-200">
                {['Product', 'Reviews', 'Avg rating', 'Health', 'Trend', 'Weakest aspect'].map(h => <th key={h} className="py-2.5 px-4 font-medium">{h}</th>)}
              </tr></thead>
              <tbody>{data.items.map(p => (
                <tr key={p.product_id} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="py-2.5 px-4 max-w-md">
                    <Link to={`/products/${p.product_id}`} className="text-brand font-medium hover:underline line-clamp-2">{p.name || p.product_id}</Link>
                    {p.name && <div className="text-xs text-ink-faint">{p.product_id}</div>}</td>
                  <td className="px-4">{p.n_reviews.toLocaleString()}</td>
                  <td className="px-4">{p.avg_rating.toFixed(2)}</td>
                  <td className={`px-4 font-semibold ${healthTone(p.health_score)}`}>{p.health_score}</td>
                  <td className="px-4"><span className={`text-xs rounded px-2 py-0.5 ${TREND[p.trend_status].cls}`}>{TREND[p.trend_status].label}</span></td>
                  <td className="px-4">{p.weakest_aspect ? `${pretty(p.weakest_aspect.aspect)} (${pct(p.weakest_aspect.positive_ratio)} positive)` : '–'}</td>
                </tr>))}</tbody>
            </table>
          </div>
          <div className="flex items-center justify-between text-sm text-ink-soft">
            <span>{offset + 1}–{offset + data.items.length} of {data.total.toLocaleString()} products</span>
            <div className="flex gap-2">
              <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} className="border border-slate-300 rounded px-3 py-1 disabled:opacity-40">Previous</button>
              <button disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)} className="border border-slate-300 rounded px-3 py-1 disabled:opacity-40">Next</button>
            </div>
          </div>
          <p className="text-xs text-ink-faint">{data.note}</p>
        </>)}
    </div>
  )
}
