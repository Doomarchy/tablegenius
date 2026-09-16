import type { DataIndex, Standings } from './types'

const base = import.meta.env.BASE_URL

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${base}data/${path}`, { cache: 'no-cache' })
  if (!res.ok) throw new Error(`Could not load ${path} (${res.status})`)
  return (await res.json()) as T
}

export const loadIndex = () => fetchJson<DataIndex>('index.json')
export const loadStandings = (season: string, code: string) =>
  fetchJson<Standings>(`${season}/${code}/standings.json`)
