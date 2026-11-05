import { describe, it, expect } from 'vitest'
import {
  distanceKm,
  isReachableAt,
  isRunLate,
  windowsWithPassedFlag,
  type WindowOut,
} from './trailSignal'

const window: WindowOut = { start_utc: '2026-11-05T10:05:00Z', end_utc: '2026-11-05T10:08:00Z' }

describe('isRunLate', () => {
  const validUntil = '2026-11-06T12:00:00Z'

  it('is false up to and at the valid until time', () => {
    expect(isRunLate(validUntil, new Date('2026-11-06T12:00:00Z'))).toBe(false)
  })

  it('is true once the valid until time has passed', () => {
    expect(isRunLate(validUntil, new Date('2026-11-06T12:00:01Z'))).toBe(true)
  })
})

describe('windowsWithPassedFlag', () => {
  it('keeps a window as current during its last minute', () => {
    const [flagged] = windowsWithPassedFlag([window], new Date('2026-11-05T10:08:30Z'))
    expect(flagged.passed).toBe(false)
  })

  it('marks a window passed after its last minute and never drops it', () => {
    const flagged = windowsWithPassedFlag([window], new Date('2026-11-05T10:09:00Z'))
    expect(flagged).toEqual([{ ...window, passed: true }])
  })
})

describe('isReachableAt', () => {
  it('is true from the first minute to the end of the last minute', () => {
    expect(isReachableAt([window], new Date('2026-11-05T10:05:00Z'))).toBe(true)
    expect(isReachableAt([window], new Date('2026-11-05T10:08:59Z'))).toBe(true)
  })

  it('is false before and after', () => {
    expect(isReachableAt([window], new Date('2026-11-05T10:04:59Z'))).toBe(false)
    expect(isReachableAt([window], new Date('2026-11-05T10:09:00Z'))).toBe(false)
  })

  it('is false with no windows', () => {
    expect(isReachableAt([], new Date('2026-11-05T10:05:00Z'))).toBe(false)
  })
})

describe('distanceKm', () => {
  it('counts 50 meters for each point', () => {
    expect(distanceKm(0)).toBe(0)
    expect(distanceKm(20)).toBe(1)
    expect(distanceKm(255)).toBeCloseTo(12.75)
  })
})
