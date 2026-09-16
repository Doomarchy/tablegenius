import { useMemo, useState, type CSSProperties } from 'react'
import { buildColumns, type Column } from '../columns'
import { dec1, formatPct, pct1, signed } from '../format'
import type { Standings, TeamRow } from '../types'
import Form from './Form'

export type TableView = 'table' | 'chances' | 'both'

const zoneShort: Record<string, string> = {
  ucl: 'UCL',
  ucl_qualifying: 'UCL Q',
  uel: 'UEL',
  uecl: 'UECL',
  relegation_playoff: 'Play-off',
  relegation: 'Rel.',
}

interface Sort {
  key: string
  dir: 'asc' | 'desc'
}

function Crest({ team }: { team: TeamRow }) {
  if (!team.crest) return <span className="crest crest-empty" aria-hidden="true" />
  return <img className="crest" src={team.crest} alt="" loading="lazy" width={22} height={22} />
}

function cellText(col: Column, v: number | null): string {
  if (v === null) return '–'
  switch (col.kind) {
    case 'prob':
      return formatPct(v)
    case 'signed':
      return signed(v)
    case 'dec1':
      return dec1(v)
    default:
      return String(v)
  }
}

export default function LeagueTable({ standings, view }: { standings: Standings; view: TableView }) {
  const { league } = standings
  const hasProbs = standings.model !== null && standings.teams.some((t) => t.probs)
  const columns = useMemo(() => buildColumns(league, hasProbs), [league, hasProbs])
  const [sort, setSort] = useState<Sort>({ key: 'position', dir: 'asc' })

  const rows = useMemo(() => {
    const list = [...standings.teams]
    if (sort.key === 'position') {
      list.sort((a, b) => (sort.dir === 'asc' ? a.position - b.position : b.position - a.position))
      return list
    }
    const col = columns.find((c) => c.key === sort.key)
    if (!col) return list
    list.sort((a, b) => {
      const va = col.value(a)
      const vb = col.value(b)
      if (va === null && vb === null) return a.position - b.position
      if (va === null) return 1
      if (vb === null) return -1
      const d = sort.dir === 'asc' ? va - vb : vb - va
      return d !== 0 ? d : a.position - b.position
    })
    return list
  }, [standings.teams, sort, columns])

  const toggleSort = (key: string, defaultAsc: boolean) => {
    setSort((s) => {
      if (s.key === key) {
        const flipped = s.dir === 'asc' ? 'desc' : 'asc'
        // Third click returns to the league order.
        const back = defaultAsc ? 'asc' : 'desc'
        return flipped === back ? { key: 'position', dir: 'asc' } : { key, dir: flipped }
      }
      return { key, dir: defaultAsc ? 'asc' : 'desc' }
    })
  }

  const visible = (col: Column) => {
    if (view === 'table') return col.group !== 'prob' && col.group !== 'exp'
    if (view === 'chances') return col.group !== 'std'
    return true
  }
  const shown = columns.filter(visible)
  const indicator = (key: string) => (sort.key === key ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : '')

  return (
    <div className={`table-wrap view-${view}`}>
      <table className="league-table">
        <thead>
          <tr>
            <th className="col-pos" scope="col" aria-sort={sort.key === 'position' ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
              <button type="button" className="th-btn" onClick={() => toggleSort('position', true)} title="League position">
                #{indicator('position')}
              </button>
            </th>
            <th className="col-team" scope="col">Team</th>
            {shown.map((col) => (
              <th
                key={col.key}
                scope="col"
                className={`col-${col.group}${col.kind === 'prob' ? ' col-prob-head' : ''}`}
                aria-sort={sort.key === col.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
              >
                <button type="button" className="th-btn" onClick={() => toggleSort(col.key, !!col.ascending)} title={col.description}>
                  {col.label}
                  {indicator(col.key)}
                </button>
              </th>
            ))}
            {view !== 'chances' && (
              <th scope="col" className="col-form col-std" title="Last five results, oldest first">Form</th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => {
            const zoneLabel = t.zone ? league.zones[t.zone]?.label : undefined
            return (
              <tr key={t.id} className={t.zone ? `zone zone-${t.zone}` : undefined}>
                <td className="col-pos">
                  <span className="pos" title={zoneLabel}>{t.position}</span>
                  {t.tied && <span className="tied" title="Level with another team and not separable by the league's criteria yet">=</span>}
                </td>
                <td className="col-team">
                  <span className="team-cell">
                    <Crest team={t} />
                    <span className="team-name" title={t.name}>
                      <span className="name-long">{t.short_name}</span>
                      <span className="name-short">{t.tla ?? t.short_name}</span>
                    </span>
                    {t.zone && <span className={`zone-tag zone-tag-${t.zone}`}>{zoneShort[t.zone]}</span>}
                  </span>
                </td>
                {shown.map((col) => {
                  const v = col.value(t)
                  if (col.kind === 'prob') {
                    const p = v ?? 0
                    const style = { '--p': p, '--hue': `var(--zone-${col.hue})` } as CSSProperties
                    return (
                      <td key={col.key} className="col-prob" style={style} title={v === null ? undefined : `${t.short_name}: ${pct1(v)} · ${col.description}`}>
                        {cellText(col, v)}
                      </td>
                    )
                  }
                  const cls = [`col-${col.group}`, col.key === 'points' ? 'col-pts' : '', col.kind === 'signed' && v !== null ? (v > 0 ? 'pos-num' : v < 0 ? 'neg-num' : '') : ''].filter(Boolean).join(' ')
                  return (
                    <td key={col.key} className={cls}>
                      {cellText(col, v)}
                    </td>
                  )
                })}
                {view !== 'chances' && (
                  <td className="col-form col-std"><Form results={t.form} /></td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
