import type { Column } from '../columns'

export default function ColumnGuide({ columns, hasProbs }: { columns: Column[]; hasProbs: boolean }) {
  return (
    <details className="assumptions">
      <summary>What the columns mean</summary>
      <dl className="guide">
        {columns.map((c) => (
          <div key={c.key}>
            <dt>{c.label}</dt>
            <dd>{c.description}</dd>
          </div>
        ))}
        <div>
          <dt>Form</dt>
          <dd>Last five results, oldest first.</dd>
        </div>
        {hasProbs && (
          <div>
            <dt>Shading</dt>
            <dd>Darker cells mean higher chances. “&lt;1” and “&gt;99” mark chances below 0.5% and above 99.5%; nothing is ever truly 0% or 100% until it is mathematically settled.</dd>
          </div>
        )}
      </dl>
    </details>
  )
}
