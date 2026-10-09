import { useEffect, useState } from 'react'
import './App.css'

type Health = {
  status: string
  service: string
  time: string
  tomtom_key_configured: boolean
}

function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/health')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((body: Health) => setHealth(body))
      .catch((e: Error) => setError(e.message))
  }, [])

  let apiStatus = 'checking…'
  if (health) {
    apiStatus = `${health.status}, TomTom key ${health.tomtom_key_configured ? 'configured' : 'missing'}`
  } else if (error) {
    apiStatus = `unreachable (${error})`
  }

  return (
    <main className="app">
      <header className="app-header">
        <h1>Weather-Aware Truck Routing</h1>
        <p className="api-status">API: {apiStatus}</p>
      </header>
    </main>
  )
}

export default App
