import { describePipeline } from '../lib/pipelineNames'
import { formatUtc, type Pipeline } from '../lib/status'
import type { PredictionsCard as PredictionsCardState } from '../lib/trailPredictions'

const STATE_LABELS: Record<Pipeline['state'], string> = {
  ok: 'Working',
  late: 'Running late',
  failed: 'Failed',
}

function StateBadge({ state }: { state: Pipeline['state'] }) {
  return <span className={`state-badge state-${state}`}>{STATE_LABELS[state]}</span>
}

export function PipelineCard({ pipeline }: { pipeline: Pipeline }) {
  const { title, about } = describePipeline(pipeline.name)
  const incidentIsSafe = pipeline.incident_url?.startsWith('https://') ?? false

  return (
    <li className="card">
      <StateBadge state={pipeline.state} />
      <h3>{title}</h3>
      {about && <p>{about}</p>}
      <dl className="facts">
        <dt>Last finished</dt>
        <dd>{formatUtc(pipeline.last_good_run_utc)}</dd>
        <dt>Schedule</dt>
        <dd>Every night. Counted as late after {pipeline.freshness_target_hours} hours.</dd>
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

export function PipelineKey() {
  return (
    <ul className="state-key" aria-label="What each state means">
      <li>
        <StateBadge state="ok" />
        The last run finished on time.
      </li>
      <li>
        <StateBadge state="late" />
        The last run is older than it should be, so the site keeps showing the last good data.
      </li>
      <li>
        <StateBadge state="failed" />
        The last run stopped with an error. I get an alert, and the site keeps showing the last good
        data.
      </li>
    </ul>
  )
}

/** The nightly trail run, built from the trail answer, so it sits first among the pipelines. */
export function PredictionsCard({ card }: { card: PredictionsCardState }) {
  return (
    <li className="card">
      {card.kind === 'ready' && <StateBadge state={card.state} />}
      <h3>Trail predictions</h3>
      <p>The nightly job that works out coverage and satellite windows for every trail.</p>
      {card.kind === 'loading' && <p>Loading the trail predictions.</p>}
      {card.kind === 'error' && <p role="alert">The trail predictions are unavailable right now.</p>}
      {card.kind === 'ready' && (
        <dl className="facts">
          <dt>Last finished</dt>
          <dd>{formatUtc(card.lastGoodRunUtc)}</dd>
          <dt>Valid until</dt>
          <dd>{formatUtc(card.validUntilUtc)}</dd>
          <dt>Schedule</dt>
          <dd>Every night at 10:00 UTC.</dd>
        </dl>
      )}
    </li>
  )
}
