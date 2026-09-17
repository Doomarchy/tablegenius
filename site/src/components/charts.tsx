import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useInks, type Inks } from '../useInks'
import type { History, LeagueMeta, ZoneKey } from '../types'

// Loose supertype of Recharts' TooltipContentProps so the same tip works for every chart.
interface TipPayload {
  name?: unknown
  value?: unknown
  color?: string
  dataKey?: unknown
  payload?: unknown
}
interface TipProps {
  active?: boolean
  payload?: ReadonlyArray<TipPayload>
  label?: unknown
}
type Row = Record<string, unknown>

function fmt(v: unknown, suffix = '%'): string {
  if (typeof v !== 'number') return String(v ?? '')
  if (suffix === '%') return v < 0.5 ? '<1%' : v > 99.5 ? '>99%' : `${Math.round(v)}%`
  return `${v}${suffix}`
}

function ChartTip({ active, payload, label, title, suffix = '%' }: TipProps & { title?: (l: unknown, row?: Row) => string; suffix?: string }) {
  if (!active || !payload || payload.length === 0) return null
  const row = payload[0]?.payload as Row | undefined
  const head = title ? title(label, row) : String(label ?? '')
  return (
    <div className="chart-tip">
      <div className="chart-tip-head">{head}</div>
      {payload.map((p, i) => (
        <div key={i} className="chart-tip-row">
          <span className="chart-tip-swatch" style={{ background: p.color }} />
          <span>{String(p.name ?? '')}</span>
          <b>{fmt(p.value, suffix)}</b>
        </div>
      ))}
    </div>
  )
}

const SERIES: { key: 'title' | 'ucl' | 'europe' | 'relegation'; name: string; dash?: string; ink: (i: Inks) => string }[] = [
  { key: 'title', name: 'Title', ink: (i) => i.scarlet },
  { key: 'ucl', name: 'Champions League', dash: '7 4', ink: (i) => i.scarlet },
  { key: 'europe', name: 'Any European place', dash: '2 4', ink: (i) => i.scarlet },
  { key: 'relegation', name: 'Relegation', ink: (i) => i.ink },
]

export function LineSample({ color, dash }: { color: string; dash?: string }) {
  return (
    <svg width="30" height="8" aria-hidden="true">
      <line x1="1" y1="4" x2="29" y2="4" stroke={color} strokeWidth="2.5" strokeDasharray={dash} strokeLinecap="round" />
    </svg>
  )
}

export function ChancesChart({ history, teamId, totalMatchdays }: { history: History; teamId: string; totalMatchdays: number }) {
  const inks = useInks()
  const data = history.snapshots
    .filter((s) => s.teams[teamId])
    .map((s) => {
      const t = s.teams[teamId]
      return { md: s.matchday, label: s.label, title: t.title * 100, ucl: t.ucl * 100, europe: t.europe * 100, relegation: t.relegation * 100 }
    })
  const last = data[data.length - 1]
  const xMax = Math.max(6, Math.min(totalMatchdays, (last?.md ?? 0) + 2))
  const axis = { fill: inks.inkSoft, fontFamily: inks.mono, fontSize: 11 }
  return (
    <div className="chart-card">
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 12, right: 16, bottom: 4, left: -12 }}>
          <CartesianGrid stroke={inks.rule} strokeDasharray="1 4" vertical={false} />
          <XAxis dataKey="md" type="number" domain={[0, xMax]} tickCount={Math.min(xMax + 1, 10)} allowDecimals={false} tick={axis} axisLine={{ stroke: inks.ink }} tickLine={false}
            tickFormatter={(v: number) => (v === 0 ? 'Pre' : String(v))} />
          <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={axis} axisLine={false} tickLine={false} tickFormatter={(v: number) => `${v}%`} width={44} />
          <Tooltip content={(p: TipProps) => <ChartTip {...p} title={(l, row) => String(row?.label ?? `Matchday ${String(l)}`)} />} cursor={{ stroke: inks.inkFaint, strokeDasharray: '3 3' }} />
          {SERIES.map((s) => (
            <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.ink(inks)} strokeWidth={2.5} strokeDasharray={s.dash}
              dot={{ r: 2.5, fill: s.ink(inks), strokeWidth: 0 }} activeDot={{ r: 5, stroke: inks.paper, strokeWidth: 2 }} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <ul className="chart-legend">
        {SERIES.map((s) => (
          <li key={s.key}>
            <LineSample color={s.ink(inks)} dash={s.dash} />
            <span>{s.name}</span>
            {last && <b>{fmt(last[s.key])}</b>}
          </li>
        ))}
      </ul>
    </div>
  )
}

function zoneOf(league: LeagueMeta, pos: number): ZoneKey | null {
  for (const key of ['ucl', 'ucl_qualifying', 'uel', 'uecl', 'relegation_playoff', 'relegation'] as ZoneKey[]) {
    const p = league.zones[key]?.positions
    if (p && pos >= p[0] && pos <= p[1]) return key
  }
  return null
}

export function PositionChart({ positions, league, current }: { positions: number[]; league: LeagueMeta; current: number }) {
  const inks = useInks()
  const data = positions.map((p, i) => ({ pos: i + 1, p: p * 100, zone: zoneOf(league, i + 1) }))
  const fill = (zone: ZoneKey | null) => {
    if (zone === 'ucl' || zone === 'ucl_qualifying') return inks.scarlet
    if (zone === 'uel' || zone === 'uecl') return inks.scarlet
    if (zone === 'relegation') return inks.ink
    if (zone === 'relegation_playoff') return inks.inkSoft
    return inks.inkFaint
  }
  const axis = { fill: inks.inkSoft, fontFamily: inks.mono, fontSize: 11 }
  const max = Math.max(...data.map((d) => d.p), 10)
  return (
    <div className="chart-card">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 12, right: 8, bottom: 4, left: -12 }} barCategoryGap={2}>
          <CartesianGrid stroke={inks.rule} strokeDasharray="1 4" vertical={false} />
          <XAxis dataKey="pos" tick={axis} axisLine={{ stroke: inks.ink }} tickLine={false} interval={0} />
          <YAxis domain={[0, Math.ceil(max / 10) * 10]} tick={axis} axisLine={false} tickLine={false} tickFormatter={(v: number) => `${v}%`} width={44} />
          <Tooltip content={(p: TipProps) => <ChartTip {...p} title={(l) => `Finish ${l}${ordinal(Number(l))}`} />} cursor={{ fill: inks.paper2 }} />
          <ReferenceLine x={current} stroke={inks.ink} strokeDasharray="3 3" label={{ value: 'now', position: 'top', fill: inks.inkSoft, fontFamily: inks.mono, fontSize: 10 }} />
          <Bar dataKey="p" name="Chance" isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.pos} fill={fill(d.zone)} opacity={d.zone ? 1 : 0.7} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <ul className="chart-legend">
        <li><span className="legend-stamp zone-ucl" /> European places</li>
        {league.zones.relegation_playoff?.positions && <li><span className="legend-stamp zone-relegation_playoff" /> Relegation play-off</li>}
        <li><span className="legend-stamp zone-relegation" /> Relegation</li>
        <li><span className="legend-stamp" /> Mid-table</li>
      </ul>
    </div>
  )
}

export function PositionHistoryChart({ history, teamId, teamCount }: { history: History; teamId: string; teamCount: number }) {
  const inks = useInks()
  const data = history.snapshots
    .filter((s) => s.matchday > 0 && s.teams[teamId])
    .map((s) => ({ md: s.matchday, label: s.label, position: s.teams[teamId].position, points: s.teams[teamId].points }))
  const last = data[data.length - 1]
  const xMax = Math.max(6, (last?.md ?? 0) + 2)
  const axis = { fill: inks.inkSoft, fontFamily: inks.mono, fontSize: 11 }
  const ticks = [1, 4, 8, 12, 16, teamCount].filter((v, i, a) => v <= teamCount && a.indexOf(v) === i)
  return (
    <div className="chart-card">
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 12, right: 16, bottom: 4, left: -12 }}>
          <CartesianGrid stroke={inks.rule} strokeDasharray="1 4" vertical={false} />
          <XAxis dataKey="md" type="number" domain={[1, xMax]} allowDecimals={false} tick={axis} axisLine={{ stroke: inks.ink }} tickLine={false} />
          <YAxis reversed domain={[1, teamCount]} ticks={ticks} tick={axis} axisLine={false} tickLine={false} width={44} />
          <Tooltip content={(p: TipProps) => <ChartTip {...p} suffix="" title={(l, row) => `${String(row?.label ?? `Matchday ${String(l)}`)} · ${String(row?.points ?? '')} pts`} />} cursor={{ stroke: inks.inkFaint, strokeDasharray: '3 3' }} />
          <Line type="stepAfter" dataKey="position" name="Position" stroke={inks.ink} strokeWidth={2.5} dot={{ r: 3, fill: inks.ink, strokeWidth: 0 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return s[(v - 20) % 10] ?? s[v] ?? s[0]
}
