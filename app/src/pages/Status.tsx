import { useEffect, useState } from 'react'
import { ColdStartNotice } from '../components/ColdStartNotice'
import { DataFreshness } from '../components/DataFreshness'
import { LateNotice } from '../components/LateNotice'
import { PipelineCard, PipelineKey } from '../components/PipelineCard'
import { trailSignalUrl, trailsUrl } from '../lib/api'
import { formatUtc, pipelinesNeedingNotice, type StatusDoc } from '../lib/status'
import type { TrailSignal, TrailSummary } from '../lib/trailSignal'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'ready'; doc: StatusDoc }

type TrailLoad =
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'ready'; signal: TrailSignal }

async function fetchFirstTrail(baseUrl: string): Promise<TrailSignal> {
  const list = await fetch(trailsUrl(baseUrl))
  if (!list.ok) throw new Error(`HTTP ${list.status}`)
  const { trails } = (await list.json()) as { trails: TrailSummary[] }
  const answer = await fetch(trailSignalUrl(baseUrl, trails[0].trail_id))
  if (!answer.ok) throw new Error(`HTTP ${answer.status}`)
  return (await answer.json()) as TrailSignal
}

export function Status() {
  const [load, setLoad] = useState<LoadState>({ kind: 'loading' })
  const [trail, setTrail] = useState<TrailLoad>({ kind: 'loading' })

  // Every trail comes from the same nightly run, so one trail answers for all of them.
  useEffect(() => {
    fetchFirstTrail(import.meta.env.VITE_API_BASE_URL)
      .then((signal) => setTrail({ kind: 'ready', signal }))
      .catch(() => setTrail({ kind: 'error' }))
  }, [])

  useEffect(() => {
    const controller = new AbortController()

    fetch('/status.json', { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json() as Promise<StatusDoc>
      })
      .then((doc) => setLoad({ kind: 'ready', doc }))
      .catch(() => {
        if (!controller.signal.aborted) setLoad({ kind: 'error' })
      })

    return () => controller.abort()
  }, [])

  return (
    <>
      <h1>Can I trust the data right now?</h1>

      {trail.kind === 'loading' && <ColdStartNotice />}
      {trail.kind === 'error' && <p role="alert">Trail data is unavailable right now.</p>}
      {trail.kind === 'ready' && (
        <DataFreshness
          lastGoodRunUtc={trail.signal.last_good_run_utc}
          validUntilUtc={trail.signal.valid_until_utc}
          now={new Date()}
        />
      )}

      <h2>Pipeline status</h2>
      <p className="lede">
        A pipeline is a job that runs by itself every night. These boxes show how each one did.
      </p>

      {load.kind === 'loading' && <p>Loading status.</p>}
      {load.kind === 'error' && <p role="alert">Status is unavailable right now.</p>}

      {load.kind === 'ready' && (
        <>
          <p>Last updated {formatUtc(load.doc.generated_at_utc)}.</p>

          {pipelinesNeedingNotice(load.doc.pipelines).map((p) => (
            <LateNotice key={p.name} pipelineName={p.name} lastGoodRunUtc={p.last_good_run_utc} />
          ))}

          <ul className="cards">
            {load.doc.pipelines.map((p) => (
              <PipelineCard key={p.name} pipeline={p} />
            ))}
          </ul>
          <PipelineKey />
        </>
      )}
    </>
  )
}
