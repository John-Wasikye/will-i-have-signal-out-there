type PipelineState = 'ok' | 'late' | 'failed'

/** One pipeline in status.json (docs/platform/contracts/status_json.yaml). */
export interface Pipeline {
  name: string
  state: PipelineState
  // Left out until a run succeeds.
  last_good_run_utc?: string
  freshness_target_hours: number
  last_row_count?: number
  incident_url?: string
}

export interface StatusDoc {
  generated_at_utc: string
  pipelines: Pipeline[]
}

/** Pipelines whose state is late or failed. Each one needs a LateNotice. */
export function pipelinesNeedingNotice(pipelines: Pipeline[]): Pipeline[] {
  return pipelines.filter((p) => p.state === 'late' || p.state === 'failed')
}

/**
 * Formats a UTC ISO string for display. Uses the reader's local time zone
 * unless a time zone name is passed (for example "UTC").
 */
export function formatUtc(iso: string | null | undefined, timeZone?: string): string {
  if (!iso) return 'No successful run yet'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return 'Unknown time'
  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone,
  }).format(date)
}
