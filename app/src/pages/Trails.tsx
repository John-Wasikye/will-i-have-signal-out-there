import { useEffect, useState } from 'react'
import { ColdStartNotice } from '../components/ColdStartNotice'
import { Credits } from '../components/Credits'
import { DtcRequirementsNote } from '../components/DtcRequirementsNote'
import { TrailSignalView } from '../components/TrailSignalView'
import { trailSignalUrl, trailsUrl } from '../lib/api'
import type { TrailSignal, TrailSummary } from '../lib/trailSignal'
import { PHASE_A_TRAILS } from '../lib/trails'

const LOAD_ERROR = 'The trail data could not be loaded. Try again.'
const MINUTE_MS = 60_000

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`The API answered ${response.status}`)
  return (await response.json()) as T
}

export function Trails() {
  const [trails, setTrails] = useState<TrailSummary[]>([])
  const [trailId, setTrailId] = useState('')
  const [signal, setSignal] = useState<TrailSignal | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [now, setNow] = useState(() => new Date())

  // Lateness and passed windows depend on the time, so they are checked again while the page is open.
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), MINUTE_MS)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    fetchJson<{ trails: TrailSummary[] }>(trailsUrl(import.meta.env.VITE_API_BASE_URL))
      .then((answer) => setTrails(answer.trails))
      .catch(() => setFailed(true))
      .finally(() => setLoading(false))
  }, [])

  function chooseTrail(id: string) {
    setTrailId(id)
    setSignal(null)
    setFailed(false)
    if (!id) return
    setLoading(true)
    fetchJson<TrailSignal>(trailSignalUrl(import.meta.env.VITE_API_BASE_URL, id))
      .then((answer) => setSignal(answer))
      .catch(() => setFailed(true))
      .finally(() => setLoading(false))
  }

  return (
    <>
      <h1>Trails</h1>
      <p>
        I cover three main trails at Grand Canyon National Park: {PHASE_A_TRAILS.join(', ')}. Pick
        one to see where T-Mobile claims coverage and when a satellite could be reachable.
      </p>

      <label htmlFor="trail">Choose a trail</label>
      <select id="trail" value={trailId} onChange={(event) => chooseTrail(event.target.value)}>
        <option value="">Choose a trail</option>
        {trails.map((trail) => (
          <option key={trail.trail_id} value={trail.trail_id}>
            {trail.trail_name ?? trail.trail_id}
          </option>
        ))}
      </select>

      {loading && <ColdStartNotice />}
      {failed && (
        <p role="alert" className="error-text">
          {LOAD_ERROR}
        </p>
      )}
      {signal && <TrailSignalView key={signal.trail_id} signal={signal} now={now} />}

      <DtcRequirementsNote />
      <Credits />
    </>
  )
}
