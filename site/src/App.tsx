import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { loadIndex } from './api'
import Layout from './components/Layout'
import AboutPage from './pages/AboutPage'
import LeaguePage from './pages/LeaguePage'
import type { DataIndex } from './types'

export default function App() {
  const [index, setIndex] = useState<DataIndex | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadIndex().then(setIndex).catch((e: Error) => setError(e.message))
  }, [])

  if (error) {
    return (
      <Layout index={null}>
        <p className="notice error">Could not load data: {error}. Run the pipeline to generate it.</p>
      </Layout>
    )
  }
  if (!index) {
    return (
      <Layout index={null}>
        <p className="notice">Loading…</p>
      </Layout>
    )
  }

  const first = index.leagues[0]?.code ?? 'PL'
  return (
    <Layout index={index}>
      <Routes>
        <Route path="/" element={<Navigate to={`/league/${first}`} replace />} />
        <Route path="/league/:code" element={<LeaguePage index={index} />} />
        <Route path="/about" element={<AboutPage index={index} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
