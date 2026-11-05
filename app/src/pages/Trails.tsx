import { useEffect, useRef, useState } from 'react'
import { ColdStartNotice } from '../components/ColdStartNotice'
import { Credits } from '../components/Credits'
import { DtcRequirementsNote } from '../components/DtcRequirementsNote'
import { TrailSignalView } from '../components/TrailSignalView'
import { trailSignalUrl, trailsUrl } from '../lib/api'
import { latestOnly } from '../lib/latestOnly'
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
  const beginRequest = useRef(latestOnly())

  // Lateness and passed windows depend on the time, so they are checked again while the page is open.
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), MINUTE_MS)
    return () => clearInterval(timer)
  }, [])

  function chooseTrail(id: string) {
    setTrailId(id)
    setSignal(null)
    setFailed(false)
    setLoading(true)
    const isCurrent = beginRequest.current()
    fetchJson<TrailSignal>(trailSignalUrl(import.meta.env.VITE_API_BASE_URL, id))
      .then((answer) => {
        if (isCurrent()) setSignal(answer)
      })
      .catch(() => {
        if (isCurrent()) setFailed(true)
      })
      .finally(() => {
        if (isCurrent()) setLoading(false)
      })
  }

  // The first trail opens by itself, so a visitor has something to try straight away.
  useEffect(() => {
    fetchJson<{ trails: TrailSummary[] }>(trailsUrl(import.meta.env.VITE_API_BASE_URL))
      .then((answer) => {
        setTrails(answer.trails)
        if (answer.trails.length > 0) chooseTrail(answer.trails[0].trail_id)
        else setLoading(false)
      })
      .catch(() => {
        setFailed(true)
        setLoading(false)
      })
  }, [])

  return (
    <>
      <h2 className="walk-heading">Walk a trail before you go</h2>
      <div className="trail-choices" role="group" aria-label="Choose a trail">
        <p className="trail-choices-label">Choose a trail</p>
        {trails.map((trail) => (
          <button
            key={trail.trail_id}
            type="button"
            className="trail-choice"
            aria-pressed={trail.trail_id === trailId}
            onClick={() => chooseTrail(trail.trail_id)}
          >
            {trail.trail_name ?? trail.trail_id}
          </button>
        ))}
      </div>

      {loading && <ColdStartNotice />}
      {failed && (
        <p role="alert" className="error-text">
          {LOAD_ERROR}
        </p>
      )}
      {signal && <TrailSignalView key={signal.trail_id} signal={signal} now={now} />}

      <p className="lede">
        I cover three main trails at Grand Canyon National Park: {PHASE_A_TRAILS.join(', ')}. Choose
        one, press walk, and watch where T-Mobile claims coverage and where a satellite could be
        reachable.
      </p>

      <DtcRequirementsNote />
      <Credits />
    </>
  )
}
