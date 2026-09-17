import type { LeagueMeta, ZoneKey } from '../types'

const order: ZoneKey[] = ['ucl', 'ucl_qualifying', 'uel', 'uecl', 'relegation_playoff', 'relegation']

function range(p: [number, number]) {
  return p[0] === p[1] ? `${p[0]}` : `${p[0]}–${p[1]}`
}

export default function ZoneLegend({ league }: { league: LeagueMeta }) {
  return (
    <ul className="legend" aria-label="Table zones">
      {order.map((key) => {
        const z = league.zones[key]
        if (!z || !z.positions) return null
        return (
          <li key={key}>
            <span className={`legend-stamp zone-${key}`} aria-hidden="true" />
            {z.label} <span className="muted">({range(z.positions)})</span>
          </li>
        )
      })}
    </ul>
  )
}
