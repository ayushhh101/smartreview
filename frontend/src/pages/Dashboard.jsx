import { useApi } from '../lib/useApi.js'
import { Stat, Loading, ErrorBlock, Empty, Card } from '../components/ui.jsx'
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, Cell, ComposedChart, Line } from 'recharts'
import { pretty } from '../lib/format.js'

const COLORS = { positive: '#0F766E', neutral: '#A16207', negative: '#B42318' }

export default function Dashboard() {
  const health = useApi('/health')
  const stats = useApi('/stats/overview')

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-ink-soft mt-1">Portfolio-wide view of customer review data.</p>
        </div>
        {health.data && (
          <div className="text-xs text-ink-soft" aria-live="polite">
            API ok · MongoDB {health.data.mongodb === 'up' ? 'connected' : 'not connected'}
          </div>
        )}
      </div>

      {stats.loading && <Loading label="Loading overview" />}
      {stats.error && <ErrorBlock error={stats.error} />}

      {stats.data && !stats.data.seeded && (
        <Empty title="No reviews loaded yet">
          <p>Sample the Amazon Musical Instruments reviews and load them into MongoDB:</p>
          <pre className="bg-slate-50 rounded p-3 text-xs overflow-x-auto">{`python -m scripts.make_subset data/Musical_Instruments.jsonl --n 100000
python -m scripts.seed_database data/reviews_100000.jsonl --meta data/meta_Musical_Instruments.jsonl`}</pre>
          <p className="text-ink-faint">Until data is loaded this dashboard stays empty on purpose; it never shows placeholder numbers.</p>
        </Empty>
      )}

      {stats.data?.seeded && <Seeded d={stats.data} />}
    </div>
  )
}

function Seeded({ d }) {
  const summary = useApi('/analytics/summary')
  const pct = v => (v == null ? 'Pending NLP' : `${v}%`)
  const series = Object.entries(d.sentiment).map(([name, value]) => ({ name, value }))
  return (
    <>
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
        <Stat label="Total reviews" value={d.total_reviews.toLocaleString()} />
        <Stat label="Products" value={d.products} />
        <Stat label="Positive" value={pct(d.positive_pct)} tone="text-pos" />
        <Stat label="Negative" value={pct(d.negative_pct)} tone="text-neg" />
        <Stat label="Active streams" value="0" hint="Streaming arrives in Phase 5" />
        <Stat label="Top complaint" value={d.top_complaint || 'Pending NLP'} />
      </div>
      {series.length > 0 && (
        <Card title="Sentiment distribution" note="Count of reviews per label, from MongoDB">
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={series}>
                <XAxis dataKey="name" /><YAxis /><Tooltip />
                <Bar dataKey="value">{series.map(s => <Cell key={s.name} fill={COLORS[s.name]} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}
      {summary.error?.code === 'not_computed' && (
        <Empty title="Aspect and trend charts need analytics">
          <pre className="bg-slate-50 rounded p-3 text-xs">python -m scripts.compute_analytics</pre>
        </Empty>)}
      {summary.data && <Analytics s={summary.data} />}
    </>
  )
}

function Analytics({ s }) {
  const aspects = s.aspects.map(a => ({ name: pretty(a.aspect), Positive: Math.round(100 * a.positive_ratio),
    Negative: Math.round(100 * a.negative_ratio), Neutral: 100 - Math.round(100 * a.positive_ratio) - Math.round(100 * a.negative_ratio), mentions: a.mentions }))
  const trend = s.trend.filter(t => t.n >= 50).map(t => ({ ...t, 'Positive %': Math.round(100 * t.positive_ratio) }))
  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <Card title="Aspect sentiment, all products" note="Share of positive / neutral / negative mentions per aspect, sorted by how often each is discussed">
        <div className="h-80"><ResponsiveContainer>
          <BarChart data={aspects} layout="vertical" margin={{ left: 40 }}>
            <XAxis type="number" domain={[0, 100]} unit="%" /><YAxis type="category" dataKey="name" width={130} />
            <Tooltip /><Legend />
            <Bar dataKey="Positive" stackId="a" fill="#0F766E" /><Bar dataKey="Neutral" stackId="a" fill="#A16207" /><Bar dataKey="Negative" stackId="a" fill="#B42318" />
          </BarChart></ResponsiveContainer></div>
      </Card>
      <Card title="Review volume and sentiment over time" note="By quarter (quarters with under 50 reviews hidden). Bars = reviews, line = % positive">
        <div className="h-80"><ResponsiveContainer>
          <ComposedChart data={trend}>
            <XAxis dataKey="period" tick={{ fontSize: 10 }} interval="preserveStartEnd" /><YAxis yAxisId="n" /><YAxis yAxisId="p" orientation="right" domain={[0, 100]} />
            <Tooltip /><Legend />
            <Bar yAxisId="n" dataKey="n" name="Reviews" fill="#CBD5E1" /><Line yAxisId="p" dataKey="Positive %" stroke="#0F766E" strokeWidth={2} dot={false} />
          </ComposedChart></ResponsiveContainer></div>
      </Card>
    </div>
  )
}
