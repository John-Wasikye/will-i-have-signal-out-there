/** One trail in GET /trails (docs/trip-planner/openapi.yaml). */
export interface TrailSummary {
  trail_id: string
  trail_name: string | null
  unit_code: string
}

/** One period when at least one satellite is reachable. The end is its last reachable minute. */
export interface WindowOut {
  start_utc: string
  end_utc: string
}

export interface CarrierCoverage {
  carrier: string
  covered: boolean
}

export interface PointSignal {
  trail_point_id: string
  seq: number
  lon: number
  lat: number
  coverage: CarrierCoverage[]
  windows: WindowOut[]
}

/** The answer from GET /trails/{trail_id}/signal. */
export interface TrailSignal {
  trail_id: string
  run_logical_date: string
  valid_until_utc: string
  last_good_run_utc: string
  min_elevation_deg: number
  carriers: string[]
  points: PointSignal[]
}

const MINUTE_MS = 60_000
const POINT_SPACING_KM = 0.05

function endOfLastMinute(window: WindowOut): number {
  return new Date(window.end_utc).getTime() + MINUTE_MS
}

/**
 * Data is late once its valid until time has passed (ADR 0027). A night with no new publish
 * reaches this too: the next run is due before the current predictions run out (ADR 0019).
 */
export function isRunLate(validUntilUtc: string, now: Date): boolean {
  return now.getTime() > new Date(validUntilUtc).getTime()
}

/** Marks each window as passed or not. Every window stays: passed ones are drawn in grey. */
export function windowsWithPassedFlag(windows: WindowOut[], now: Date) {
  return windows.map((window) => ({ ...window, passed: now.getTime() >= endOfLastMinute(window) }))
}

export function isReachableAt(windows: WindowOut[], now: Date): boolean {
  const time = now.getTime()
  return windows.some(
    (window) => new Date(window.start_utc).getTime() <= time && time < endOfLastMinute(window),
  )
}

/** How far along the trail line a point is. Points are sampled every 50 meters. */
export function distanceKm(seq: number): number {
  return seq * POINT_SPACING_KM
}
