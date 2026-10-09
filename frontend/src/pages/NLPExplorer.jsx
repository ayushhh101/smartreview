import { useState } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { useApi } from '../lib/useApi.js'
import { api } from '../lib/api.js'
import { pretty } from '../lib/format.js'
import { Stat, Loading, ErrorBlock, Empty, Card, Badge } from '../components/ui.jsx'

const EXAMPLES = [
  'The tone is great but the strap broke after two weeks.',
  "I bought a Fender Stratocaster guitar and Ernie Ball strings. They didn't disappoint, the sound is really amazing!",
  'Terrible sound, cheap build, but easy setup and fair price.',
  'I like the piano.. but the sustain pedal failed after less than 1 year. I expected better support.',
]
const ENT = { BRAND: 'bg-blue-50 text-brand border-blue-200', INSTRUMENT: 'bg-teal-50 text-pos border-teal-200', GEAR: 'bg-amber-50 text-neu border-amber-200', PROPER_NOUN: 'bg-slate-100 text-ink-soft border-slate-200' }
const LAB = { positive: 'text-pos', negative: 'text-neg', neutral: 'text-neu' }

export default function NLPExplorer() {
  const [tab, setTab] = useState('analyze')
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">NLP Explorer</h1>
        <div className="mt-2 flex gap-2"><Badge>NLP</Badge><Badge>Every pipeline step, on any text</Badge></div>
      </div>
      <div className="flex gap-2" role="tablist">
        {[['analyze', 'Analyze a review'], ['corpus', 'Corpus insights']].map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={`text-sm rounded px-4 py-1.5 border ${tab === k ? 'bg-brand text-white border-brand' : 'border-slate-300 bg-white'}`}>{l}</button>))}
      </div>
      {tab === 'analyze' ? <Analyze /> : <Corpus />}
    </div>
  )
}

function Analyze() {
  const [text, setText] = useState(EXAMPLES[0])
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const run = async (t = text) => {
    setBusy(true); setErr(null)
    try { setRes(await api('/nlp/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: t }) })) }
    catch (e) { setErr(e); setRes(null) } finally { setBusy(false) }
  }
  return (
    <>
      <Card title="Input" note="Paste any review. Each classic NLP step is shown below.">
        <textarea value={text} onChange={e => setText(e.target.value)} rows={3} maxLength={2000} aria-label="Review text"
          className="w-full border border-slate-300 rounded p-2 text-sm" />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button onClick={() => run()} disabled={busy || text.trim().length < 2} className="bg-brand text-white text-sm rounded px-4 py-1.5 disabled:opacity-40">{busy ? 'Analyzing…' : 'Analyze'}</button>
          {EXAMPLES.map((e, i) => <button key={i} onClick={() => { setText(e); run(e) }} className="text-xs border border-slate-300 rounded px-2 py-1 hover:bg-slate-50">Example {i + 1}</button>)}
        </div>
        {err && <div className="mt-3"><ErrorBlock error={err} /></div>}
      </Card>
      {res && <Result r={res} />}
    </>
  )
}

const Chip = ({ children, cls = 'bg-slate-100 text-ink border-slate-200' }) => <span className={`inline-block text-xs border rounded px-2 py-0.5 mr-1.5 mb-1.5 ${cls}`}>{children}</span>

function Result({ r }) {
  const words = r.tokens.filter(t => !t.is_punct)
  const [showAll, setShowAll] = useState(false)
  const rows = showAll ? words : words.slice(0, 25)
  const o = r.sentiment.overall
  return (
    <>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Sentences / words" value={`${r.n_sentences} / ${r.n_words}`} />
        <Stat label="Stop words removed" value={r.stop_word_count} hint="Negations such as 'not' are kept" />
        <Stat label="Lexicon sentiment (VADER)" value={o.label} tone={LAB[o.label]} hint={`compound ${o.compound}`} />
        <Stat label="Trained classifier" value={r.model ? r.model.label : 'not trained'} tone={r.model && LAB[r.model.label]}
          hint={r.model ? (r.model.agrees_with_lexicon ? 'agrees with lexicon' : 'differs from lexicon') : 'run scripts.train_models'} />
      </div>

      <Card title="1. Tokens, POS tags, stems and lemmas" note="Porter, Snowball and Lancaster stemmers cut words by rules and can produce non-words; the WordNet lemmatiser uses the POS tag to return a real word.">
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead><tr className="text-left text-ink-soft border-b border-slate-200">{['Token', 'POS', 'Meaning', 'Stop word', 'Porter', 'Snowball', 'Lancaster', 'Lemma'].map(h => <th key={h} className="py-1.5 pr-3 font-medium">{h}</th>)}</tr></thead>
          <tbody>{rows.map((t, i) => (
            <tr key={i} className={`border-b border-slate-100 ${t.is_stop ? 'text-ink-faint' : ''}`}>
              <td className="py-1 pr-3 font-medium">{t.text}</td><td className="pr-3">{t.pos}</td><td className="pr-3 text-ink-soft">{t.pos_meaning}</td>
              <td className="pr-3">{t.is_stop ? 'yes' : ''}</td><td className="pr-3">{t.porter}</td><td className="pr-3">{t.snowball}</td><td className="pr-3">{t.lancaster}</td>
              <td className={`pr-3 ${t.lemma !== t.lower ? 'text-brand font-medium' : ''}`}>{t.lemma}</td></tr>))}</tbody>
        </table></div>
        {words.length > 25 && <button onClick={() => setShowAll(!showAll)} className="mt-2 text-xs text-brand hover:underline">{showAll ? 'Show fewer' : `Show all ${words.length} tokens`}</button>}
      </Card>

      <div className="grid lg:grid-cols-2 gap-6">
        <Card title="2. Model input" note="Exactly what the classifier sees: stop words removed, lemmatised, plus n-grams for TF-IDF">
          <div>{r.model_input.lemmas.length ? r.model_input.lemmas.map((l, i) => <Chip key={i}>{l}</Chip>) : <span className="text-sm text-ink-faint">No content words</span>}</div>
          {r.model_input.bigrams.length > 0 && <><div className="text-xs text-ink-soft mt-2 mb-1">Bigrams</div><div>{r.model_input.bigrams.map((l, i) => <Chip key={i} cls="bg-blue-50 text-brand border-blue-200">{l}</Chip>)}</div></>}
          {r.tfidf_top && <><div className="text-xs text-ink-soft mt-2 mb-1">Highest TF-IDF weights (from the trained model's vectoriser)</div>
            <div>{r.tfidf_top.map((t, i) => <Chip key={i} cls="bg-teal-50 text-pos border-teal-200">{t.term} {t.weight}</Chip>)}</div></>}
        </Card>
        <Card title="3. Chunking: noun phrases and opinion pairs" note="A regular-expression grammar over POS tags finds noun phrases; adjective-noun links are candidate opinions">
          <div className="text-xs text-ink-soft mb-1">Noun phrases</div>
          <div>{r.noun_phrases.length ? r.noun_phrases.map((p, i) => <Chip key={i}>{p}</Chip>) : <span className="text-sm text-ink-faint">none</span>}</div>
          <div className="text-xs text-ink-soft mt-2 mb-1">Opinion pairs</div>
          {r.opinion_pairs.length ? r.opinion_pairs.map((p, i) => <div key={i} className="text-sm">{p.adjective} → {p.noun} <span className="text-xs text-ink-faint">({p.pattern})</span></div>) : <span className="text-sm text-ink-faint">none</span>}
        </Card>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <Card title="4. Named entities" note="Dictionary NER for brands, instruments and gear, plus a proper-noun heuristic. It only finds what the lists contain.">
          {r.entities.length ? r.entities.map((e, i) => <Chip key={i} cls={ENT[e.type]}>{e.text} <b>· {pretty(e.type)}</b></Chip>) : <span className="text-sm text-ink-faint">No entities found</span>}
        </Card>
        <Card title="5. Sentiment by sentence" note="VADER compound score, -1 (very negative) to +1 (very positive)">
          {r.sentiment.sentences.map((s, i) => (
            <div key={i} className="text-sm mb-1.5"><span className={`font-medium ${LAB[s.label]}`}>{s.compound > 0 ? '+' : ''}{s.compound}</span> <span className="text-ink-soft">{s.sentence}</span></div>))}
        </Card>
      </div>

      <Card title="6. Aspect-based sentiment" note="The review is split into clauses (at punctuation and words like 'but'). Each clause with an aspect word is scored.">
        {r.aspects.details.length === 0 ? <p className="text-sm text-ink-faint">No aspect words found.</p> : (
          <table className="w-full text-sm"><thead><tr className="text-left text-ink-soft border-b border-slate-200">{['Aspect', 'Trigger words', 'Clause', 'Score', 'Label'].map(h => <th key={h} className="py-1.5 pr-3 font-medium">{h}</th>)}</tr></thead>
            <tbody>{r.aspects.details.map((d, i) => (
              <tr key={i} className="border-b border-slate-100"><td className="py-1.5 pr-3 capitalize font-medium">{pretty(d.aspect)}</td><td className="pr-3">{d.triggers.join(', ')}</td>
                <td className="pr-3 text-ink-soft">{d.clause}</td><td className="pr-3">{d.score}</td><td className={`pr-3 font-medium ${LAB[d.label]}`}>{d.label}</td></tr>))}</tbody></table>)}
      </Card>
    </>
  )
}

function Corpus() {
  const { data: d, error, loading } = useApi('/nlp/corpus')
  if (loading) return <Loading label="Loading corpus statistics" />
  if (error?.code === 'not_computed') return (
    <Empty title="Corpus statistics not computed yet">
      <p>Compute vocabulary, Zipf, distinctive words, collocations, topics and word vectors from the reviews in MongoDB:</p>
      <pre className="bg-slate-50 rounded p-3 text-xs">python -m scripts.compute_nlp_stats</pre></Empty>)
  if (error) return <ErrorBlock error={error} />
  return (
    <>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Reviews analysed" value={d.n_reviews.toLocaleString()} />
        <Stat label="Tokens" value={d.tokens_total.toLocaleString()} hint={`${d.avg_tokens_per_review} per review`} />
        <Stat label="Vocabulary: raw → lemmas" value={`${d.vocab_raw.toLocaleString()} → ${d.vocab_lemma.toLocaleString()}`} hint={`${d.vocab_reduction_pct}% smaller after stop words + lemmatisation`} />
        <Stat label="Words seen only once" value={`${d.hapax_pct_of_vocab}%`} hint={`type-token ratio ${d.type_token_ratio}`} />
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <Card title="Zipf's law" note={`Rank vs frequency on log-log axes. Fitted slope ${d.zipf.slope} (R² ${d.zipf.r2}); natural language is close to -1.`}>
          <div className="h-64"><ResponsiveContainer><LineChart data={d.zipf.points}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" /><XAxis dataKey="rank" type="number" scale="log" domain={['dataMin', 'dataMax']} /><YAxis scale="log" domain={['auto', 'auto']} /><Tooltip />
            <Line dataKey="freq" stroke="#2B4C9B" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div>
        </Card>
        <Card title="Most mentioned nouns and adjectives" note="Number of reviews containing each lemma">
          <div>{d.top_keywords.slice(0, 24).map(k => <Chip key={k.term}>{k.term} <b className="text-ink-soft">{k.count.toLocaleString()}</b></Chip>)}</div>
        </Card>
      </div>

      <Card title="Distinctive words per sentiment class" note="Log-odds with an informative Dirichlet prior (z-score). Higher = more characteristic of that class than of the rest.">
        <div className="grid md:grid-cols-3 gap-6">
          {['negative', 'neutral', 'positive'].map(c => (
            <div key={c}><div className={`font-medium capitalize mb-1 ${LAB[c]}`}>{c}</div>
              <div className="text-xs text-ink-soft mb-1">Words</div>{d.distinctive_unigrams[c].map(t => <div key={t.term} className="text-sm">{t.term} <span className="text-xs text-ink-faint">z {t.z}</span></div>)}
              <div className="text-xs text-ink-soft mt-2 mb-1">Word pairs</div>{d.distinctive_bigrams[c].slice(0, 6).map(t => <div key={t.term} className="text-sm">{t.term} <span className="text-xs text-ink-faint">z {t.z}</span></div>)}
            </div>))}
        </div>
      </Card>

      <div className="grid lg:grid-cols-2 gap-6">
        <Card title="Collocations (PMI)" note="Word pairs that occur together far more often than chance">
          <table className="w-full text-sm"><thead><tr className="text-left text-ink-soft border-b border-slate-200"><th className="py-1.5 font-medium">Pair</th><th className="font-medium">PMI</th><th className="font-medium">Count</th></tr></thead>
            <tbody>{d.collocations.slice(0, 12).map(c => <tr key={c.bigram} className="border-b border-slate-100"><td className="py-1">{c.bigram}</td><td>{c.pmi}</td><td>{c.count.toLocaleString()}</td></tr>)}</tbody></table>
        </Card>
        <SimilarWords />
      </div>

      {/* <Card title="Topics (NMF on TF-IDF)" note={`Unsupervised, ${d.topic_sample_size.toLocaleString()}-review sample. Topic names are for a human to choose. Negative share shows which themes carry complaints.`}>
        <table className="w-full text-sm"><thead><tr className="text-left text-ink-soft border-b border-slate-200">{['#', 'Top words', 'Reviews', 'Share', 'Avg rating', 'Negative'].map(h => <th key={h} className="py-1.5 pr-3 font-medium">{h}</th>)}</tr></thead>
          <tbody>{d.topics.map(t => (
            <tr key={t.topic} className="border-b border-slate-100"><td className="py-1.5 pr-3">{t.topic}</td><td className="pr-3">{t.top_words.join(', ')}</td>
              <td className="pr-3">{t.n_reviews.toLocaleString()}</td><td className="pr-3">{Math.round(100 * t.share)}%</td><td className="pr-3">{t.avg_rating}</td>
              <td className={`pr-3 font-medium ${t.negative_share > 0.2 ? 'text-neg' : ''}`}>{Math.round(100 * t.negative_share)}%</td></tr>))}</tbody></table>
      </Card> */}
    </>
  )
}

function SimilarWords() {
  const [w, setW] = useState('tone')
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const go = async () => { setErr(null); try { setRes(await api(`/nlp/similar-words?word=${encodeURIComponent(w.trim().toLowerCase())}&k=8`)) } catch (e) { setErr(e); setRes(null) } }
  return (
    <Card title="Similar words (LSA embeddings)" note="Word vectors from TruncatedSVD on the TF-IDF matrix. Classic distributional semantics, not Word2Vec.">
      <div className="flex gap-2">
        <input value={w} onChange={e => setW(e.target.value)} onKeyDown={e => e.key === 'Enter' && go()} aria-label="Word" className="border border-slate-300 rounded px-2 py-1.5 text-sm w-40" />
        <button onClick={go} disabled={w.trim().length < 2} className="bg-brand text-white text-sm rounded px-4 py-1.5 disabled:opacity-40">Find</button>
      </div>
      {err && <p className="text-sm text-neg mt-2">{err.message || 'Not found'}</p>}
      {res && <div className="mt-3">{res.neighbors.map(n => <div key={n.word} className="text-sm">{n.word} <span className="text-xs text-ink-faint">{n.similarity}</span></div>)}</div>}
    </Card>
  )
}
