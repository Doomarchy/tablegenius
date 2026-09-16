export function formatUpdated(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const diffMin = Math.round((Date.now() - date.getTime()) / 60000)
  let rel: string
  if (diffMin < 1) rel = 'just now'
  else if (diffMin < 60) rel = `${diffMin} min ago`
  else if (diffMin < 60 * 48) rel = `${Math.round(diffMin / 60)} h ago`
  else rel = `${Math.round(diffMin / 1440)} days ago`
  const abs = date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
  return `${rel} · ${abs}`
}

export const signed = (n: number) => (n > 0 ? `+${n}` : String(n))

/** Whole-number percentage for table cells; extremes are shown as "<1" and ">99". */
export function formatPct(p: number): string {
  if (p >= 1) return '100'
  if (p <= 0) return '0'
  if (p < 0.005) return '<1'
  if (p > 0.995) return '>99'
  return String(Math.round(p * 100))
}

export const pct1 = (p: number) => `${(p * 100).toFixed(1)}%`
export const dec1 = (n: number) => n.toFixed(1)
export const dec2 = (n: number) => n.toFixed(2)
