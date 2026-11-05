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
const HOUR_MS = 60 * MINUTE_MS
const WALK_STEPS = 160
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

/** What a hiker can do at a point: use the carrier, reach a satellite now, or neither. */
export type PointState = 'covered' | 'satellite' | 'none'

export interface TrailRun {
  state: PointState
  start: number
  end: number
}

export interface MapPoint {
  x: number
  y: number
}

/** Late data never claims a satellite right now, because its windows can no longer be trusted. */
export function pointState(point: PointSignal, now: Date, late: boolean): PointState {
  if (point.coverage.some((item) => item.covered)) return 'covered'
  return !late && isReachableAt(point.windows, now) ? 'satellite' : 'none'
}

/** Groups neighbouring points that share a state, so each stretch is drawn as one line. */
export function trailRuns(states: PointState[]): TrailRun[] {
  const runs: TrailRun[] = []
  states.forEach((state, index) => {
    const last = runs[runs.length - 1]
    if (last?.state === state) last.end = index
    else runs.push({ state, start: index, end: index })
  })
  return runs
}

/**
 * Fits a trail into a map of the given size, with north at the top. A degree of longitude is
 * shorter than a degree of latitude away from the equator, so longitude is scaled to match.
 */
export function trailShape(
  points: PointSignal[],
  width: number,
  height: number,
  padding: number,
): MapPoint[] {
  const lons = points.map((point) => point.lon)
  const lats = points.map((point) => point.lat)
  const [minLon, maxLon] = [Math.min(...lons), Math.max(...lons)]
  const [minLat, maxLat] = [Math.min(...lats), Math.max(...lats)]
  const squeeze = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180)
  const spanX = (maxLon - minLon) * squeeze
  const spanY = maxLat - minLat
  const scale = Math.min(
    (width - 2 * padding) / (spanX || 1),
    (height - 2 * padding) / (spanY || 1),
  )
  const offsetX = (width - spanX * scale) / 2
  const offsetY = (height - spanY * scale) / 2
  return points.map((point) => ({
    x: offsetX + (point.lon - minLon) * squeeze * scale,
    y: height - offsetY - (point.lat - minLat) * scale,
  }))
}

export function nearestPoint(shape: MapPoint[], x: number, y: number): number {
  let best = 0
  let bestDistance = Infinity
  shape.forEach((point, index) => {
    const distance = (point.x - x) ** 2 + (point.y - y) ** 2
    if (distance < bestDistance) {
      best = index
      bestDistance = distance
    }
  })
  return best
}

/** The window that is open now, or else the next one. */
export function nextWindow(windows: WindowOut[], now: Date): WindowOut | undefined {
  return windows.find((window) => now.getTime() < endOfLastMinute(window))
}

/** One step of the walk. Long trails take bigger steps, so every walk lasts about as long. */
export function nextWalkStep(index: number, lastIndex: number): number {
  return Math.min(index + Math.max(1, Math.round(lastIndex / WALK_STEPS)), lastIndex)
}

/** How much of the time between the last good run and the valid until time is left. */
export function freshness(lastGoodRunUtc: string, validUntilUtc: string, now: Date) {
  const start = new Date(lastGoodRunUtc).getTime()
  const end = new Date(validUntilUtc).getTime()
  const left = Math.max(end - now.getTime(), 0)
  return {
    hoursLeft: left / HOUR_MS,
    shareLeft: Math.min(left / (end - start), 1),
    late: isRunLate(validUntilUtc, now),
  }
}

/** How far along the trail line a point is. Points are sampled every 50 meters. */
export function distanceKm(seq: number): number {
  return seq * POINT_SPACING_KM
}
