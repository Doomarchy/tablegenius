import type { FormResult } from '../types'

const label: Record<FormResult, string> = { W: 'Win', D: 'Draw', L: 'Loss' }

export default function Form({ results }: { results: FormResult[] }) {
  if (results.length === 0) return <span className="muted">–</span>
  return (
    <span className="form" aria-label={`Last ${results.length}: ${results.map((r) => label[r]).join(', ')}`}>
      {results.map((r, i) => (
        <span key={i} className={`form-pip form-${r}`} title={label[r]}>
          {r}
        </span>
      ))}
    </span>
  )
}
