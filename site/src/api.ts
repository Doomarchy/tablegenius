import type { Backtest, DataIndex, History, MatchesFile, Standings } from './types'

const base = import.meta.env.BASE_URL

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${base}data/${path}`, { cache: 'no-cache' })
  if (!res.ok) throw new Error(`Could not load ${path} (${res.status})`)
  return (await res.json()) as T
}

export const loadIndex = () => fetchJson<DataIndex>('index.json')
export const loadStandings = (season: string, code: string) =>
  fetchJson<Standings>(`${season}/${code}/standings.json`)
export const loadMatches = (season: string, code: string) =>
  fetchJson<MatchesFile>(`${season}/${code}/matches.json`)
export const loadHistory = (season: string, code: string) =>
  fetchJson<History>(`${season}/${code}/history.json`)
export const loadBacktest = () => fetchJson<Backtest>('backtest.json')
