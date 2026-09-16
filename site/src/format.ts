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
