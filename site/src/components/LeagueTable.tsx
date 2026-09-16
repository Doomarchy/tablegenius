import { signed } from '../format'
import type { Standings, TeamRow } from '../types'
import Form from './Form'

const zoneShort: Record<string, string> = {
  ucl: 'UCL',
  ucl_qualifying: 'UCL Q',
  uel: 'UEL',
  uecl: 'UECL',
  relegation_playoff: 'Play-off',
  relegation: 'Rel.',
}

function Crest({ team }: { team: TeamRow }) {
  if (!team.crest) return <span className="crest crest-empty" aria-hidden="true" />
  return <img className="crest" src={team.crest} alt="" loading="lazy" width={22} height={22} />
}

export default function LeagueTable({ standings }: { standings: Standings }) {
  const zones = standings.league.zones
  return (
    <div className="table-wrap">
      <table className="league-table">
        <thead>
          <tr>
            <th className="col-pos" scope="col" title="Position">#</th>
            <th className="col-team" scope="col">Team</th>
            <th scope="col" title="Played">P</th>
            <th scope="col" title="Won">W</th>
            <th scope="col" title="Drawn">D</th>
            <th scope="col" title="Lost">L</th>
            <th scope="col" className="col-gf" title="Goals for">GF</th>
            <th scope="col" className="col-ga" title="Goals against">GA</th>
            <th scope="col" title="Goal difference">GD</th>
            <th scope="col" className="col-pts" title="Points">Pts</th>
            <th scope="col" className="col-form" title="Last five results, oldest first">Form</th>
          </tr>
        </thead>
        <tbody>
          {standings.teams.map((t) => {
            const zoneLabel = t.zone ? zones[t.zone]?.label : undefined
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
                <td>{t.played}</td>
                <td>{t.won}</td>
                <td>{t.drawn}</td>
                <td>{t.lost}</td>
                <td className="col-gf">{t.gf}</td>
                <td className="col-ga">{t.ga}</td>
                <td className={t.gd > 0 ? 'pos-num' : t.gd < 0 ? 'neg-num' : undefined}>{signed(t.gd)}</td>
                <td className="col-pts">{t.points}</td>
                <td className="col-form"><Form results={t.form} /></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
