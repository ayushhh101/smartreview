export const Card = ({ title, note, children, className = '' }) => (
  <section className={`bg-white border border-slate-200 rounded-lg ${className}`}>
    {title && <header className="px-5 pt-4 pb-2"><h2 className="font-medium">{title}</h2>
      {note && <p className="text-xs text-ink-faint mt-0.5">{note}</p>}</header>}
    <div className="px-5 pb-5 pt-2">{children}</div>
  </section>
)

export const Stat = ({ label, value, hint, tone }) => (
  <div className="bg-white border border-slate-200 rounded-lg px-4 py-3">
    <div className="text-sm text-ink-soft">{label}</div>
    <div className={`text-2xl font-semibold mt-1 ${tone || ''}`}>{value}</div>
    {hint && <div className="text-xs text-ink-faint mt-1">{hint}</div>}
  </div>
)

export const Loading = ({ label = 'Loading' }) =>
  <div role="status" className="text-sm text-ink-soft py-6">{label}…</div>

export const ErrorBlock = ({ error }) => (
  <div role="alert" className="border border-red-200 bg-red-50 rounded-lg p-4 text-sm">
    <div className="font-medium text-neg">{error.message}</div>
    {error.hint && <div className="text-ink-soft mt-1">{error.hint}</div>}
  </div>
)

export const Empty = ({ title, children }) => (
  <div className="border border-dashed border-slate-300 rounded-lg p-6 bg-white">
    <div className="font-medium">{title}</div>
    <div className="text-sm text-ink-soft mt-2 space-y-1">{children}</div>
  </div>
)

export const Badge = ({ children, tone = 'slate' }) => {
  const tones = { slate: 'bg-slate-100 text-ink-soft', edu: 'bg-amber-50 text-neu border border-amber-200' }
  return <span className={`inline-block text-xs rounded px-2 py-0.5 ${tones[tone]}`}>{children}</span>
}
