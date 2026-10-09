import { NavLink } from 'react-router-dom'

export const NAV = [
  { to: '/', label: 'Dashboard' }, { to: '/products', label: 'Products' },
  { to: '/reviews', label: 'Reviews' }, { to: '/nlp', label: 'NLP Explorer' },
  { to: '/ml', label: 'ML Lab' }, { to: '/bda', label: 'BDA Lab' },
  { to: '/streaming', label: 'Streaming' }, { to: '/recommendations', label: 'Recommendations' },
  // { to: '/ask', label: 'Ask SmartReview' }, { to: '/mapping', label: 'Academic Mapping' },
  { to: '/about', label: 'About' },
]

export default function Sidebar() {
  return (
    <aside className="w-60 shrink-0 bg-rail text-rail-text flex flex-col min-h-screen">
      <div className="px-5 py-5 border-b border-rail-line">
        <div className="text-white font-semibold text-lg tracking-tight">SmartReview</div>
        <div className="text-xs mt-0.5">Review intelligence platform</div>
      </div>
      <nav className="p-3 flex-1 space-y-0.5" aria-label="Main">
        {NAV.map(n => (
          <NavLink key={n.to} to={n.to} end={n.to === '/'}
            className={({ isActive }) =>
              `block rounded px-3 py-2 text-sm ${isActive ? 'bg-rail-line text-white font-medium' : 'hover:bg-rail-line/60 hover:text-white'}`}>
            {n.label}
          </NavLink>
        ))}
      </nav>
      <div className="px-5 py-4 border-t border-rail-line text-xs">BDA + NLP + ML mini-project</div>
    </aside>
  )
}
