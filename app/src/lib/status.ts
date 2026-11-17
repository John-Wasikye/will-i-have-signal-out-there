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

// dateStyle and timeStyle cannot be combined with timeZoneName, so the same look is spelled out.
const DATE_AND_TIME: Intl.DateTimeFormatOptions = {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
}
const TIME_ONLY: Intl.DateTimeFormatOptions = { hour: 'numeric', minute: '2-digit' }
const DATE_ONLY: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric', year: 'numeric' }

function format(date: Date, options: Intl.DateTimeFormatOptions, timeZone?: string): string {
  return new Intl.DateTimeFormat('en-US', { ...options, timeZone }).format(date)
}

function zoneName(date: Date, timeZone?: string): string | undefined {
  return new Intl.DateTimeFormat('en-US', { timeZone, timeZoneName: 'short' })
    .formatToParts(date)
    .find((part) => part.type === 'timeZoneName')?.value
}

/**
 * Formats a UTC ISO string for display, ending with the short time zone name so a reader knows
 * which clock it is. Uses the reader's local time zone unless a time zone name is passed (for
 * example "UTC").
 */
export function formatUtc(iso: string | null | undefined, timeZone?: string): string {
  if (!iso) return 'No successful run yet'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return 'Unknown time'
  return format(date, { ...DATE_AND_TIME, timeZoneName: 'short' }, timeZone)
}

/**
 * Formats a start and an end. When both fall on one day and one clock, the date and the zone are
 * said once, because "Nov 5, 2026, 6:00 AM EST to Nov 5, 2026, 8:00 AM EST" is hard to read.
 */
export function formatUtcRange(startIso: string, endIso: string, timeZone?: string): string {
  const start = new Date(startIso)
  const end = new Date(endIso)
  const sameClock =
    !Number.isNaN(start.getTime()) &&
    !Number.isNaN(end.getTime()) &&
    format(start, DATE_ONLY, timeZone) === format(end, DATE_ONLY, timeZone) &&
    zoneName(start, timeZone) === zoneName(end, timeZone)
  if (!sameClock) return `${formatUtc(startIso, timeZone)} to ${formatUtc(endIso, timeZone)}`
  return `${format(start, DATE_AND_TIME, timeZone)} to ${format(end, { ...TIME_ONLY, timeZoneName: 'short' }, timeZone)}`
}

/** What is left of the predictions, in whole minutes rounded down, as a phrase for a sentence. */
export function describeTimeLeft(minutes: number): string {
  if (minutes < 1) return 'less than a minute'
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  const parts = [
    hours > 0 ? `${hours} ${hours === 1 ? 'hour' : 'hours'}` : '',
    rest > 0 ? `${rest} ${rest === 1 ? 'minute' : 'minutes'}` : '',
  ]
  return `another ${parts.filter(Boolean).join(' ')}`
}
