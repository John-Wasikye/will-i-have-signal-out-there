import { describe, it, expect } from 'vitest'
import { nextNightlyRun } from './nextRun'

const next = (now: string): string => nextNightlyRun(new Date(now)).toISOString()

describe('nextNightlyRun', () => {
  it('is 10:00 UTC the same day when it is earlier than that', () => {
    expect(next('2026-11-16T04:30:00Z')).toBe('2026-11-16T10:00:00.000Z')
  })

  it('is 10:00 UTC the next day when 10:00 UTC has passed', () => {
    expect(next('2026-11-16T10:00:01Z')).toBe('2026-11-17T10:00:00.000Z')
  })

  it('is the following day at exactly 10:00:00 UTC, because that run has started', () => {
    expect(next('2026-11-16T10:00:00.000Z')).toBe('2026-11-17T10:00:00.000Z')
  })

  it('is still the same day one millisecond before 10:00 UTC', () => {
    expect(next('2026-11-16T09:59:59.999Z')).toBe('2026-11-16T10:00:00.000Z')
  })

  it('rolls over the end of a month and a year', () => {
    expect(next('2026-12-31T23:00:00Z')).toBe('2027-01-01T10:00:00.000Z')
  })
})
