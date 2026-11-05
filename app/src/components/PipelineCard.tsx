import { formatUtc, type Pipeline } from '../lib/status'

const STATE_LABELS: Record<Pipeline['state'], string> = {
  ok: 'Working',
  late: 'Running late',
  failed: 'Failed',
}

const SYSTEM_CHECK = {
  title: 'Nightly system check',
  about:
    'A small test job that proves the nightly system works from start to finish. It does not make the trail predictions: those are covered at the top of this page.',
}

const KNOWN_PIPELINES: Record<string, typeof SYSTEM_CHECK> = {
  platform_skeleton: SYSTEM_CHECK,
  sample_pipeline: SYSTEM_CHECK,
}

function plainName(codeName: string): string {
  const words = codeName.replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

function StateBadge({ state }: { state: Pipeline['state'] }) {
  return <span className={`state-badge state-${state}`}>{STATE_LABELS[state]}</span>
}

export function PipelineCard({ pipeline }: { pipeline: Pipeline }) {
  const known = KNOWN_PIPELINES[pipeline.name]
  const incidentIsSafe = pipeline.incident_url?.startsWith('https://') ?? false

  return (
    <li className="card">
      <StateBadge state={pipeline.state} />
      <h3>{known?.title ?? plainName(pipeline.name)}</h3>
      {known && <p>{known.about}</p>}
      <dl className="facts">
        <dt>Last finished</dt>
        <dd>{formatUtc(pipeline.last_good_run_utc)}</dd>
        <dt>Schedule</dt>
        <dd>Should run at least every {pipeline.freshness_target_hours} hours</dd>
      </dl>
      {pipeline.last_row_count !== undefined && (
        <p className="note-text">Test records checked: {pipeline.last_row_count}</p>
      )}
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
