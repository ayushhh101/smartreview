import { useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { useApi } from '../lib/useApi.js'
import { api } from '../lib/api.js'
import { Stat, Loading, ErrorBlock, Empty, Card, Badge } from '../components/ui.jsx'

const pretty = s => s.replace(/_/g, ' ')
const f3 = v => (v == null ? '–' : Number(v).toFixed(3))

export default function MLLab() {
  const { data, error, loading } = useApi('/ml/model-comparison')
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">ML Lab</h1>
      </div>
      {loading && <Loading label="Loading model results" />}
      {error && error.code === 'not_trained' && (
        <Empty title="No models trained yet">
          <p>Train the classifiers on the reviews in MongoDB:</p>
          <pre className="bg-slate-50 rounded p-3 text-xs overflow-x-auto">python -m scripts.train_models --max-docs 20000 --folds 3</pre>
        </Empty>
      )}
      {error && error.code !== 'not_trained' && <ErrorBlock error={error} />}
      {data && <Results d={data} />}
    </div>
  )
}

function Results({ d }) {
  const best = d.models.find(m => m.is_best)
  const chart = d.models.map(m => ({ name: pretty(m.model_name), 'CV macro-F1': m.cv_mean_f1, 'Test macro-F1': m.metrics.macro_f1 }))
  return (
    <>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Best model (by CV)" value={pretty(best.model_name)} />
        <Stat label="Test macro-F1" value={f3(best.metrics.macro_f1)} hint={`Majority baseline: ${f3(d.baseline.macro_f1)}`} />
        <Stat label="Test accuracy" value={f3(best.metrics.accuracy)} hint={`Majority baseline: ${f3(d.baseline.accuracy)}`} />
        <Stat label="Reviews (train / test)" value={`${best.n_train.toLocaleString()} / ${best.n_test.toLocaleString()}`} />
      </div>
      <p className="text-xs text-ink-faint">{d.label_note} Test products are never in the training set. {d.selection_rule}.</p>

      <Card title="Model comparison" note="Macro-F1 weights negative / neutral / positive equally, so the 5-star majority cannot hide weak classes">
        <div className="h-64"><ResponsiveContainer>
          <BarChart data={chart}><XAxis dataKey="name" /><YAxis domain={[0, 1]} /><Tooltip /><Legend />
            <Bar dataKey="CV macro-F1" fill="#2B4C9B" /><Bar dataKey="Test macro-F1" fill="#0F766E" /></BarChart>
        </ResponsiveContainer></div>
        <div className="overflow-x-auto mt-4">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-ink-soft border-b border-slate-200">
              {['Model', 'Accuracy', 'Macro P', 'Macro R', 'Macro F1', 'ROC-AUC (macro)', 'CV F1 ± sd', 'Fit time'].map(h => <th key={h} className="py-2 pr-4 font-medium">{h}</th>)}
            </tr></thead>
            <tbody>{d.models.map(m => (
              <tr key={m.model_name} className="border-b border-slate-100">
                <td className="py-2 pr-4 font-medium">{pretty(m.model_name)} {m.is_best && <Badge tone="edu">best</Badge>}</td>
                <td className="pr-4">{f3(m.metrics.accuracy)}</td><td className="pr-4">{f3(m.metrics.macro_precision)}</td>
                <td className="pr-4">{f3(m.metrics.macro_recall)}</td><td className="pr-4">{f3(m.metrics.macro_f1)}</td>
                <td className="pr-4">{f3(m.metrics.roc_auc_ovr.macro)}</td>
                <td className="pr-4">{f3(m.cv_mean_f1)} ± {f3(m.cv_std_f1)}</td><td>{m.train_seconds}s</td>
              </tr>))}</tbody>
          </table>
        </div>
      </Card>

      <div className="grid lg:grid-cols-2 gap-6">
        <Confusion models={d.models} />
        <PerClass model={best} />
      </div>
      <TryIt />
    </>
  )
}

function Confusion({ models }) {
  const [name, setName] = useState(models.find(m => m.is_best).model_name)
  const m = models.find(x => x.model_name === name)
  const max = Math.max(...m.confusion_matrix.flat(), 1)
  return (
    <Card title="Confusion matrix" note="Rows = true label (from stars), columns = predicted. Test set.">
      <select aria-label="Model" value={name} onChange={e => setName(e.target.value)} className="border border-slate-300 rounded px-2 py-1 text-sm mb-3">
        {models.map(x => <option key={x.model_name} value={x.model_name}>{pretty(x.model_name)}</option>)}
      </select>
      <table className="text-sm text-center">
        <thead><tr><th></th>{m.labels.map(l => <th key={l} className="px-3 py-1 font-medium text-ink-soft">{l}</th>)}</tr></thead>
        <tbody>{m.confusion_matrix.map((row, i) => (
          <tr key={i}><th className="pr-3 text-right font-medium text-ink-soft">{m.labels[i]}</th>
            {row.map((v, j) => (
              <td key={j} className="px-4 py-3 border border-white rounded"
                  style={{ background: `rgba(43,76,155,${(0.08 + 0.8 * v / max).toFixed(2)})`, color: v / max > 0.5 ? '#fff' : '#16202C' }}>{v.toLocaleString()}</td>))}
          </tr>))}</tbody>
      </table>
    </Card>
  )
}

function PerClass({ model }) {
  return (
    <Card title={`Per-class results: ${pretty(model.model_name)}`} note="Neutral (3-star) is usually the hardest class: 3-star text is genuinely mixed">
      <table className="w-full text-sm">
        <thead><tr className="text-left text-ink-soft border-b border-slate-200">{['Class', 'Precision', 'Recall', 'F1', 'Support', 'AUC'].map(h => <th key={h} className="py-2 font-medium">{h}</th>)}</tr></thead>
        <tbody>{Object.entries(model.metrics.per_class).map(([l, v]) => (
          <tr key={l} className="border-b border-slate-100"><td className="py-2 font-medium">{l}</td><td>{f3(v.precision)}</td><td>{f3(v.recall)}</td>
            <td>{f3(v.f1)}</td><td>{v.support.toLocaleString()}</td><td>{f3(model.metrics.roc_auc_ovr[l])}</td></tr>))}</tbody>
      </table>
    </Card>
  )
}

function TryIt() {
  const [text, setText] = useState('')
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    setBusy(true); setErr(null); setRes(null)
    const post = (p) => api(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) })
    try {
      const [pred, exp] = await Promise.all([post('/ml/predict'), post('/ml/explain').catch(() => null)])
      setRes({ pred, exp })
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  const scores = res && (res.pred.probabilities || res.pred.decision_scores)
  return (
    <Card title="Try it" note="Runs your text through the NLP pipeline, then the best model; explanation comes from the logistic regression">
      <textarea value={text} onChange={e => setText(e.target.value)} rows={3} maxLength={5000} aria-label="Review text"
        placeholder="e.g. The tone is great but the strap broke after two weeks" className="w-full border border-slate-300 rounded p-2 text-sm" />
      <button onClick={run} disabled={busy || text.trim().length < 3} className="mt-2 bg-brand text-white text-sm rounded px-4 py-1.5 disabled:opacity-40">
        {busy ? 'Analyzing…' : 'Predict sentiment'}</button>
      {err && <div className="mt-3"><ErrorBlock error={err} /></div>}
      {res && (
        <div className="mt-4 text-sm space-y-2">
          <div>Predicted: <b>{res.pred.label}</b> <span className="text-ink-faint">({pretty(res.pred.model || 'best model')})</span></div>
          <div className="text-ink-soft">{res.pred.probabilities ? 'Probabilities' : 'Decision scores (not probabilities)'}: {Object.entries(scores).map(([k, v]) => `${k} ${v}`).join(' · ')}</div>
          {res.exp && (
            <div className="grid sm:grid-cols-2 gap-4">
              <Terms title={`Pushed toward "${res.exp.predicted}"`} items={res.exp.supporting} tone="text-pos" />
              <Terms title="Pushed against" items={res.exp.opposing} tone="text-neg" />
            </div>)}
        </div>)}
    </Card>
  )
}

const Terms = ({ title, items, tone }) => (
  <div><div className="font-medium">{title}</div>
    {items.length === 0 ? <div className="text-ink-faint">none</div> :
      <ul>{items.map(t => <li key={t.term} className={tone}>{t.term} <span className="text-ink-faint">{t.weight}</span></li>)}</ul>}
  </div>
)
