import { useEffect, useRef, useState } from 'react'
import { ColdStartNotice } from '../components/ColdStartNotice'
import { Credits } from '../components/Credits'
import { DtcRequirementsNote } from '../components/DtcRequirementsNote'
import { ReportButtons } from '../components/ReportButtons'
import { ReportCounts } from '../components/ReportCounts'
import { TrailSignalView } from '../components/TrailSignalView'
import { reportCountsUrl, trailSignalUrl, trailsUrl } from '../lib/api'
import { latestOnly } from '../lib/latestOnly'
import type { ReportCount } from '../lib/reportCounts'
import type { TrailSignal, TrailSummary } from '../lib/trailSignal'
import { useNow } from '../lib/useNow'
import { usePageTitle } from '../lib/usePageTitle'

const LOAD_ERROR = 'The trail data could not be loaded. Try again.'

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`The API answered ${response.status}`)
  return (await response.json()) as T
}

export function Trails() {
  usePageTitle('Trails')
  const [trails, setTrails] = useState<TrailSummary[]>([])
  const [trailId, setTrailId] = useState('')
  const [signal, setSignal] = useState<TrailSignal | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [counts, setCounts] = useState<ReportCount[] | null>(null)
  const [countsFailed, setCountsFailed] = useState(false)
  const now = useNow()
  const beginRequest = useRef(latestOnly())

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
    // The counts load on their own, so a failure here never hides the trail map.
    setCounts(null)
    setCountsFailed(false)
    fetchJson<{ counts: ReportCount[] }>(reportCountsUrl(import.meta.env.VITE_API_BASE_URL, id))
      .then((answer) => {
        if (isCurrent()) setCounts(answer.counts)
      })
      .catch(() => {
        if (isCurrent()) setCountsFailed(true)
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
      <p className="lede">
        Choose a trail, pick your carrier, and press "Walk the trail". The map then shows where that
        carrier claims coverage, using the map of the Federal Communications Commission (FCC), and,
        on T-Mobile, when a satellite text could get through.
      </p>
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
      <ReportCounts counts={counts} failed={countsFailed} />

      <ReportButtons />

      <DtcRequirementsNote />
      <Credits />
    </>
  )
}
