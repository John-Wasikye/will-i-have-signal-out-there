import { useState, type FormEvent } from 'react'
import { AnswerCard, type SampleRow } from '../components/AnswerCard'
import { ColdStartNotice } from '../components/ColdStartNotice'
import { LateNotice } from '../components/LateNotice'
import { sampleUrl } from '../lib/api'

const NOT_FOUND_MESSAGE = 'No sample row with that key.'
const GENERIC_ERROR_MESSAGE = 'Something went wrong. Try again.'

type LookupResult =
  | { kind: 'row'; row: SampleRow }
  | { kind: 'error'; message: string }

async function fetchSample(key: string): Promise<LookupResult> {
  try {
    const response = await fetch(sampleUrl(import.meta.env.VITE_API_BASE_URL, key))
    if (response.status === 404) return { kind: 'error', message: NOT_FOUND_MESSAGE }
    if (!response.ok) return { kind: 'error', message: GENERIC_ERROR_MESSAGE }
    return { kind: 'row', row: (await response.json()) as SampleRow }
  } catch {
    return { kind: 'error', message: GENERIC_ERROR_MESSAGE }
  }
}

export function Lookup() {
  const [key, setKey] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<LookupResult | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLoading(true)
    setResult(null)
    setResult(await fetchSample(key.trim()))
    setLoading(false)
  }

  return (
    <>
      <h1>Lookup</h1>
      <p>Enter a sample key to see its value and when it was last refreshed.</p>

      <form onSubmit={handleSubmit} className="lookup-form">
        <label htmlFor="sample-key">Sample key</label>
        <input
          id="sample-key"
          name="key"
          type="text"
          value={key}
          onChange={(event) => setKey(event.target.value)}
          required
          autoComplete="off"
        />
        <button type="submit" disabled={loading}>
          Submit
        </button>
      </form>

      {loading && <ColdStartNotice />}

      {result?.kind === 'error' && (
        <p role="alert" className="error-text">
          {result.message}
        </p>
      )}

      {result?.kind === 'row' && (
        <>
          <AnswerCard row={result.row} />
          {result.row.late && <LateNotice lastGoodRunUtc={result.row.last_good_run_utc} />}
        </>
      )}
    </>
  )
}
