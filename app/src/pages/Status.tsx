import { useEffect, useState } from 'react'
import { LateNotice } from '../components/LateNotice'
import { formatUtc, pipelinesNeedingNotice, type Pipeline, type StatusDoc } from '../lib/status'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'ready'; doc: StatusDoc }

export function Status() {
  const [load, setLoad] = useState<LoadState>({ kind: 'loading' })

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
      <h1>Pipeline status</h1>

      {load.kind === 'loading' && <p>Loading status.</p>}
      {load.kind === 'error' && <p role="alert">Status is unavailable right now.</p>}

      {load.kind === 'ready' && (
        <>
          <p>Generated {formatUtc(load.doc.generated_at_utc)}.</p>

          {pipelinesNeedingNotice(load.doc.pipelines).map((p) => (
            <LateNotice key={p.name} pipelineName={p.name} lastGoodRunUtc={p.last_good_run_utc} />
          ))}

          <ul className="cards">
            {load.doc.pipelines.map((p) => (
              <PipelineCard key={p.name} pipeline={p} />
            ))}
          </ul>
        </>
      )}
    </>
  )
}

function PipelineCard({ pipeline }: { pipeline: Pipeline }) {
  const incidentIsSafe = pipeline.incident_url?.startsWith('https://') ?? false

  return (
    <li className="card">
      <h2>{pipeline.name}</h2>
      <dl className="facts">
        <dt>State</dt>
        <dd>{pipeline.state}</dd>
        <dt>Last good run</dt>
        <dd>{formatUtc(pipeline.last_good_run_utc)}</dd>
        <dt>Freshness target</dt>
        <dd>{pipeline.freshness_target_hours} hours</dd>
        <dt>Last row count</dt>
        <dd>{pipeline.last_row_count ?? 'Not available'}</dd>
      </dl>
      {incidentIsSafe && (
        <p>
          <a href={pipeline.incident_url} rel="noopener noreferrer">
            Open incident
          </a>
        </p>
      )}
    </li>
  )
}
