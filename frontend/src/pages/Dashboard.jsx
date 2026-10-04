import { useApi } from '../lib/useApi.js'
import { Stat, Loading, ErrorBlock, Empty, Card } from '../components/ui.jsx'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

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
    </>
  )
}
