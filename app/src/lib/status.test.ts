import { describe, it, expect } from 'vitest'
import { formatUtc, pipelinesNeedingNotice, type Pipeline } from './status'

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
})

describe('formatUtc', () => {
  it('formats a UTC timestamp in the requested time zone', () => {
    const text = formatUtc('2026-10-08T06:00:00Z', 'UTC')
    expect(text).toContain('Oct 8, 2026')
    expect(text).toContain('6:00')
  })

  it('says there was no successful run when the value is missing', () => {
    expect(formatUtc(null)).toBe('No successful run yet')
    expect(formatUtc('')).toBe('No successful run yet')
  })

  it('says the time is unknown when the value cannot be parsed', () => {
    expect(formatUtc('not a date')).toBe('Unknown time')
  })
})
