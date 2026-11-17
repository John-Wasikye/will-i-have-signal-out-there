import { describe, it, expect } from 'vitest'
import { formatUtc, formatUtcRange, pipelinesNeedingNotice, type Pipeline } from './status'

const base: Pipeline = {
  name: 'sample_pipeline',
  state: 'ok',
  last_good_run_utc: '2026-10-08T06:00:00Z',
  freshness_target_hours: 26,
  last_row_count: 3,
}

describe('pipelinesNeedingNotice', () => {
  it('returns only the late and failed pipelines', () => {
    const pipelines: Pipeline[] = [
      base,
      { ...base, name: 'late_one', state: 'late' },
      { ...base, name: 'failed_one', state: 'failed' },
    ]
    expect(pipelinesNeedingNotice(pipelines).map((p) => p.name)).toEqual(['late_one', 'failed_one'])
  })

  it('accepts a pipeline with no good run, written as the pipeline writes it', () => {
    // pipelines/platform/publish/status.py leaves out the run time and row count until a
    // run succeeds, as the status_json contract allows.
    const neverRan: Pipeline = { name: 'new_pipeline', state: 'failed', freshness_target_hours: 26 }
    expect(pipelinesNeedingNotice([neverRan])).toEqual([neverRan])
  })
})

describe('formatUtcRange', () => {
  it('says the date and the zone once when both ends are on the same day', () => {
    expect(formatUtcRange('2026-11-05T11:00:00Z', '2026-11-05T13:00:00Z', 'America/New_York')).toBe(
      'Nov 5, 2026, 6:00 AM to 8:00 AM EST',
    )
  })

  it('gives both full times when the range crosses midnight', () => {
    expect(formatUtcRange('2026-11-05T23:00:00Z', '2026-11-06T01:00:00Z', 'UTC')).toBe(
      'Nov 5, 2026, 11:00 PM UTC to Nov 6, 2026, 1:00 AM UTC',
    )
  })

  it('gives both full times when the clocks change inside the day', () => {
    expect(formatUtcRange('2026-11-01T05:30:00Z', '2026-11-01T06:30:00Z', 'America/New_York')).toBe(
      'Nov 1, 2026, 1:30 AM EDT to Nov 1, 2026, 1:30 AM EST',
    )
  })

  it('falls back to the single value messages when an end is missing or unreadable', () => {
    expect(formatUtcRange('not a date', '2026-11-05T13:00:00Z')).toBe('Unknown time to ' + formatUtc('2026-11-05T13:00:00Z'))
  })
})

describe('formatUtc', () => {
  it('formats a UTC timestamp in the requested time zone', () => {
    const text = formatUtc('2026-10-08T06:00:00Z', 'UTC')
    expect(text).toContain('Oct 8, 2026')
    expect(text).toContain('6:00')
  })

  it('ends with the short time zone name, UTC when UTC is asked for', () => {
    expect(formatUtc('2026-10-08T06:00:00Z', 'UTC')).toBe('Oct 8, 2026, 6:00 AM UTC')
  })

  it('names the zone the reader is in, with the right winter or summer name', () => {
    expect(formatUtc('2026-11-17T12:00:00Z', 'America/New_York')).toBe('Nov 17, 2026, 7:00 AM EST')
    expect(formatUtc('2026-07-17T12:00:00Z', 'America/New_York')).toBe('Jul 17, 2026, 8:00 AM EDT')
  })

  it('uses the same look in the reader zone when no zone is passed', () => {
    expect(formatUtc('2026-11-17T12:00:00Z')).toMatch(/^Nov 1[67], 2026, \d{1,2}:00 [AP]M \S+$/)
  })

  it('says there was no successful run when the value is missing', () => {
    expect(formatUtc(null)).toBe('No successful run yet')
    expect(formatUtc('')).toBe('No successful run yet')
  })

  it('says the time is unknown when the value cannot be parsed', () => {
    expect(formatUtc('not a date')).toBe('Unknown time')
  })
})
