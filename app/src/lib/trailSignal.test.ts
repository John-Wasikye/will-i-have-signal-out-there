import { describe, it, expect } from 'vitest'
import {
  distanceKm,
  freshness,
  isReachableAt,
  isRunLate,
  nearestPoint,
  nextWalkStep,
  nextWindow,
  coveredPointCount,
  pointState,
  startingCarrier,
  trailRuns,
  trailShape,
  windowsWithPassedFlag,
  type PointSignal,
  type WindowOut,
} from './trailSignal'

const window: WindowOut = { start_utc: '2026-11-05T10:05:00Z', end_utc: '2026-11-05T10:08:00Z' }

const mapPoint = (lon: number, lat: number, covered: boolean, windows: WindowOut[]): PointSignal => ({
  trail_point_id: `p-${lon}`,
  seq: 0,
  lon,
  lat,
  coverage: [{ carrier: 'T-Mobile', covered }],
  windows,
})

const open = { start_utc: '2026-11-05T11:00:00Z', end_utc: '2026-11-05T13:00:00Z' }
const later = { start_utc: '2026-11-05T15:00:00Z', end_utc: '2026-11-05T16:00:00Z' }
const gone = { start_utc: '2026-11-05T09:00:00Z', end_utc: '2026-11-05T09:30:00Z' }
const noon = new Date('2026-11-05T12:00:00Z')

describe('pointState', () => {
  it('says covered wherever the carrier claims coverage, whatever the satellite does', () => {
    expect(pointState(mapPoint(0, 0, true, [open]), 'T-Mobile', noon, false)).toBe('covered')
  })

  it('says satellite where there is no coverage but a satellite is reachable now', () => {
    expect(pointState(mapPoint(0, 0, false, [open]), 'T-Mobile', noon, false)).toBe('satellite')
  })

  it('says none where neither works now', () => {
    expect(pointState(mapPoint(0, 0, false, [later]), 'T-Mobile', noon, false)).toBe('none')
  })

  it('counts only the chosen carrier, not any carrier', () => {
    const point = {
      ...mapPoint(0, 0, false, [later]),
      coverage: [
        { carrier: 'AT&T', covered: true },
        { carrier: 'T-Mobile', covered: false },
      ],
    }
    expect(pointState(point, 'T-Mobile', noon, false)).toBe('none')
    expect(pointState(point, 'AT&T', noon, false)).toBe('covered')
  })

  it('never claims a satellite when the data is late', () => {
    expect(pointState(mapPoint(0, 0, false, [open]), 'T-Mobile', noon, true)).toBe('none')
  })
})

describe('trailRuns', () => {
  it('groups neighbouring points that share a state', () => {
    expect(trailRuns(['covered', 'covered', 'none', 'satellite', 'satellite'])).toEqual([
      { state: 'covered', start: 0, end: 1 },
      { state: 'none', start: 2, end: 2 },
      { state: 'satellite', start: 3, end: 4 },
    ])
  })

  it('has no runs for no points', () => {
    expect(trailRuns([])).toEqual([])
  })
})

describe('trailShape', () => {
  const points = [mapPoint(-112, 36, true, []), mapPoint(-111.9, 36.1, true, [])]
  const shape = trailShape(points, 600, 400, 20)

  it('keeps every point inside the padded map', () => {
    for (const { x, y } of shape) {
      expect(x).toBeGreaterThanOrEqual(20)
      expect(x).toBeLessThanOrEqual(580)
      expect(y).toBeGreaterThanOrEqual(20)
      expect(y).toBeLessThanOrEqual(380)
    }
  })

  it('draws north at the top', () => {
    expect(shape[1].y).toBeLessThan(shape[0].y)
  })

  it('squeezes east and west by latitude, so the shape is not stretched', () => {
    const wide = (shape[1].x - shape[0].x) / (shape[0].y - shape[1].y)
    expect(wide).toBeCloseTo(Math.cos((36.05 * Math.PI) / 180), 2)
  })

  it('does not fail on a single point', () => {
    const [only] = trailShape([points[0]], 600, 400, 20)
    expect(Number.isFinite(only.x)).toBe(true)
    expect(Number.isFinite(only.y)).toBe(true)
  })
})

describe('nearestPoint', () => {
  it('finds the point closest to a tap', () => {
    const shape = [{ x: 0, y: 0 }, { x: 50, y: 50 }, { x: 100, y: 0 }]
    expect(nearestPoint(shape, 90, 10)).toBe(2)
  })
})

describe('nextWindow', () => {
  it('skips passed windows', () => {
    expect(nextWindow([gone, later], noon)).toBe(later)
  })

  it('counts a window that is open now', () => {
    expect(nextWindow([gone, open, later], noon)).toBe(open)
  })

  it('has nothing to offer when every window has passed', () => {
    expect(nextWindow([gone], noon)).toBeUndefined()
  })
})

describe('nextWalkStep', () => {
  it('moves forward', () => {
    expect(nextWalkStep(10, 400)).toBeGreaterThan(10)
  })

  it('stops at the end of the trail', () => {
    expect(nextWalkStep(399, 400)).toBe(400)
  })

  it('crosses any trail in about the same time', () => {
    expect(nextWalkStep(0, 200)).toBeLessThan(nextWalkStep(0, 800))
  })
})

describe('freshness', () => {
  const lastRun = '2026-11-05T00:00:00Z'
  const validUntil = '2026-11-06T00:00:00Z'

  it('says how much of the predictions time is left', () => {
    const result = freshness(lastRun, validUntil, noon)
    expect(result.hoursLeft).toBe(12)
    expect(result.shareLeft).toBeCloseTo(0.5)
    expect(result.late).toBe(false)
  })

  it('never goes below nothing once the data is late', () => {
    const result = freshness(lastRun, validUntil, new Date('2026-11-07T00:00:00Z'))
    expect(result.hoursLeft).toBe(0)
    expect(result.shareLeft).toBe(0)
    expect(result.late).toBe(true)
  })
})

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

describe('startingCarrier', () => {
  const all = ['AT&T', 'T-Mobile', 'Verizon']

  it('starts on the carrier the phone remembers for reports', () => {
    expect(startingCarrier(all, 'Verizon')).toBe('Verizon')
  })

  it('starts on T-Mobile, the satellite texting carrier, when the phone remembers none', () => {
    expect(startingCarrier(all, null)).toBe('T-Mobile')
  })

  it('ignores a remembered carrier the data does not have', () => {
    expect(startingCarrier(['AT&T', 'T-Mobile'], 'Verizon')).toBe('T-Mobile')
  })

  it('falls back to the first carrier when T-Mobile is missing', () => {
    expect(startingCarrier(['AT&T', 'Verizon'], null)).toBe('AT&T')
  })
})

describe('coveredPointCount', () => {
  it('counts the points where the chosen carrier claims coverage', () => {
    const points = [true, false, true].map((covered, n) => ({
      ...mapPoint(n, 0, covered, []),
      coverage: [
        { carrier: 'AT&T', covered: true },
        { carrier: 'T-Mobile', covered },
      ],
    }))
    expect(coveredPointCount(points, 'T-Mobile')).toBe(2)
    expect(coveredPointCount(points, 'AT&T')).toBe(3)
  })
})
