import { useCallback, useEffect, useRef, useState } from 'react'
import type { captureCell as CaptureCell } from '../lib/cell'
import { reportsUrl } from '../lib/api'
import {
  CARRIERS,
  buildReport,
  enqueueReport,
  flushQueue,
  getOrCreateVisitorId,
  loadCarrier,
  loadQueue,
  saveCarrier,
  sendReport,
  waitingNote,
  type Carrier,
  type FlushSummary,
  type KeyValueStore,
} from '../lib/reports'

const POSITION_OPTIONS: PositionOptions = { enableHighAccuracy: true, timeout: 30_000, maximumAge: 60_000 }
const LOCATION_DENIED =
  'I need your location to know where you are. Allow location for this site and try again.'
const LOCATION_FAILED = 'Your phone could not find its position. Try again with a clear view of the sky.'
const CELL_TOOL_MISSING =
  'The page did not finish loading before signal was lost. Open it again when you have signal.'
const NO_LOCATION = 'This browser cannot share a location, so it cannot send reports.'

/** localStorage when the browser allows it; otherwise a store that lasts only while the page is open. */
function phoneStore(): KeyValueStore {
  try {
    const probe = 'signal.probe'
    window.localStorage.setItem(probe, probe)
    window.localStorage.removeItem(probe)
    return window.localStorage
  } catch {
    const data = new Map<string, string>()
    return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => void data.set(key, value) }
  }
}

function outcome(summary: FlushSummary): string {
  const parts: string[] = []
  if (summary.accepted > 0) {
    parts.push(`Thank you. ${summary.accepted === 1 ? 'Your report was' : `${summary.accepted} reports were`} sent.`)
  }
  parts.push(...summary.refused)
  return parts.join(' ')
}

/** "I had signal here" and "I had no signal here" (C21, FR-49 to FR-52). */
export function ReportButtons() {
  const [carrier, setCarrier] = useState<Carrier | ''>('')
  const [waiting, setWaiting] = useState(0)
  const [message, setMessage] = useState('')
  const store = useRef<KeyValueStore | null>(null)
  const sending = useRef(false)
  const cellModule = useRef<Promise<{ captureCell: typeof CaptureCell }> | null>(null)

  const flush = useCallback(async () => {
    const phone = store.current
    if (phone === null || sending.current) return
    sending.current = true
    try {
      const visitorId = getOrCreateVisitorId(phone, (length) =>
        crypto.getRandomValues(new Uint8Array(length)),
      )
      const summary = await flushQueue(
        phone,
        (report) => sendReport(reportsUrl(import.meta.env.VITE_API_BASE_URL), visitorId, report, fetch),
        new Date(),
      )
      setWaiting(summary.waiting)
      const said = outcome(summary)
      if (said) setMessage(said)
    } finally {
      sending.current = false
    }
  }, [])

  // Saved reports go out when the page opens, when the connection returns, and when the hiker
  // comes back to the tab. Sending in the background on Android is part 2 (a service worker).
  useEffect(() => {
    // Load h3-js now, while there is signal, so a tap works later without it.
    cellModule.current = import('../lib/cell')
    store.current = phoneStore()
    setCarrier(loadCarrier(store.current) ?? '')
    setWaiting(loadQueue(store.current).length)
    void flush()
    const whenVisible = () => {
      if (document.visibilityState === 'visible') void flush()
    }
    const whenOnline = () => void flush()
    window.addEventListener('online', whenOnline)
    document.addEventListener('visibilitychange', whenVisible)
    return () => {
      window.removeEventListener('online', whenOnline)
      document.removeEventListener('visibilitychange', whenVisible)
    }
  }, [flush])

  function chooseCarrier(value: string) {
    const chosen = CARRIERS.find((option) => option === value)
    if (chosen === undefined || store.current === null) return
    setCarrier(chosen)
    saveCarrier(store.current, chosen)
  }

  function report(hadSignal: boolean) {
    const phone = store.current
    if (phone === null) return
    if (carrier === '') {
      setMessage('Pick your carrier first.')
      return
    }
    if (!('geolocation' in navigator)) {
      setMessage(NO_LOCATION)
      return
    }
    setMessage('Finding your position...')
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        let cell: string
        try {
          cell = (await (cellModule.current ?? import('../lib/cell'))).captureCell(position)
        } catch {
          setMessage(CELL_TOOL_MISSING)
          return
        }
        setWaiting(enqueueReport(phone, buildReport(cell, carrier, hadSignal, new Date()), crypto.randomUUID()))
        setMessage('Saved on your phone. It will be sent when you have signal.')
        void flush()
      },
      (error) => setMessage(error.code === error.PERMISSION_DENIED ? LOCATION_DENIED : LOCATION_FAILED),
      POSITION_OPTIONS,
    )
  }

  return (
    <section className="panel report-panel" aria-labelledby="report-heading">
      <h2 id="report-heading">Tell other hikers</h2>
      <p>
        Did you have signal where you are standing? Your phone turns your position into an area about
        350 m across and sends only that area, your carrier, and the hour. Your exact position never
        leaves your phone.
      </p>
      <label className="report-carrier">
        Your carrier{' '}
        <select value={carrier} onChange={(event) => chooseCarrier(event.target.value)}>
          <option value="" disabled>
            Choose
          </option>
          {CARRIERS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
      <div className="report-buttons">
        <button type="button" className="trail-choice" onClick={() => report(true)}>
          I had signal here
        </button>
        <button type="button" className="trail-choice" onClick={() => report(false)}>
          I had no signal here
        </button>
      </div>
      <p aria-live="polite" className="report-status">
        {[message, waitingNote(waiting)].filter(Boolean).join(' ')}
      </p>
      <p className="report-help">
        With no signal, a report waits on your phone and goes out when signal returns, the next time
        this page is open.
      </p>
    </section>
  )
}
