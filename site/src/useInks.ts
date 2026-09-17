import { useEffect, useState } from 'react'

export interface Inks {
  scarlet: string
  ink: string
  inkSoft: string
  inkFaint: string
  paper: string
  paper2: string
  paper3: string
  rule: string
  mono: string
  display: string
}

function read(): Inks {
  const cs = getComputedStyle(document.documentElement)
  const v = (name: string, fallback: string) => cs.getPropertyValue(name).trim() || fallback
  return {
    scarlet: v('--scarlet', '#cc0033'),
    ink: v('--ink', '#1b1917'),
    inkSoft: v('--ink-soft', '#5f5850'),
    inkFaint: v('--ink-faint', '#9a9184'),
    paper: v('--paper', '#f3efe7'),
    paper2: v('--paper-2', '#eae4d8'),
    paper3: v('--paper-3', '#dbd2c1'),
    rule: v('--rule', '#cfc7b7'),
    mono: v('--font-mono', '"IBM Plex Mono", monospace'),
    display: v('--font-display', '"Barlow Condensed", sans-serif'),
  }
}

/** The current theme's ink colours, re-read when the theme toggles (SVG charts cannot use CSS variables reliably). */
export function useInks(): Inks {
  const [inks, setInks] = useState<Inks>(read)
  useEffect(() => {
    const obs = new MutationObserver(() => setInks(read()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => obs.disconnect()
  }, [])
  return inks
}
