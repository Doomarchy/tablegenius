import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { formatUpdated } from '../format'
import type { DataIndex } from '../types'
import ThemeToggle from './ThemeToggle'

export default function Layout({ index, children }: { index: DataIndex | null; children: ReactNode }) {
  return (
    <div className="app">
      <header className="header">
        <div className="header-row">
          <NavLink to="/" className="brand">
            <span className="brand-mark">TG</span>
            <span className="brand-name">TableGenius</span>
          </NavLink>
          <div className="header-actions">
            {index && (
              <span className="updated" title="Time of the last data update">
                Updated {formatUpdated(index.updated_at)}
              </span>
            )}
            <NavLink to="/about" className={({ isActive }) => `about-link${isActive ? ' active' : ''}`}>
              About
            </NavLink>
            <ThemeToggle />
          </div>
        </div>
        {index && (
          <nav className="tabs" aria-label="Leagues">
            {index.leagues.map((l) => (
              <NavLink key={l.code} to={`/league/${l.code}`} className={({ isActive }) => `tab${isActive ? ' active' : ''}`}>
                {l.name}
              </NavLink>
            ))}
          </nav>
        )}
      </header>
      <main className="main">{children}</main>
      <footer className="footer">
        <p>
          Results and fixtures from <a href="https://www.football-data.org" rel="noopener">football-data.org</a>. Historical results from{' '}
          <a href="https://www.football-data.co.uk" rel="noopener">football-data.co.uk</a>. Probabilities are model estimates, not predictions of fact.
        </p>
      </footer>
    </div>
  )
}
