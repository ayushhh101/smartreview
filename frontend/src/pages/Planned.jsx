import { Empty, Badge } from '../components/ui.jsx'

export default function Planned({ title, subject, phase, children }) {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <div className="mt-2 flex gap-2"><Badge>{subject}</Badge><Badge>Phase {phase}</Badge></div>
      </div>
      <Empty title="Not built yet">{children}</Empty>
    </div>
  )
}
