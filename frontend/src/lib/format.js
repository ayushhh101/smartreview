export const pretty = s => (s || '').replace(/_/g, ' ')
export const pct = v => (v == null ? '–' : `${Math.round(v * 100)}%`)
export const healthTone = s => (s >= 70 ? 'text-pos' : s >= 50 ? 'text-neu' : 'text-neg')
export const TREND = {
  emerging_negative: { label: 'Emerging negative trend', cls: 'bg-red-50 text-neg border border-red-200' },
  improving: { label: 'Improving', cls: 'bg-teal-50 text-pos border border-teal-200' },
  stable: { label: 'Stable', cls: 'bg-slate-100 text-ink-soft' },
  insufficient_data: { label: 'Not enough data for a trend', cls: 'bg-slate-100 text-ink-faint' },
}
