import { describe, it, expect } from 'vitest'
import tripPlannerContract from '../../../docs/trip-planner/openapi.yaml?raw'
import { reportCountsUrl, reportsUrl, trailSignalUrl, trailsUrl } from './api'

function pathOf(url: string): string {
  return new URL(url).pathname
}

const tripPlannerPaths = [...tripPlannerContract.matchAll(/^ {2}(\/[^:\s]*):\s*$/gm)].map(
  (match) => match[1],
)

describe('trailsUrl', () => {
  it('asks for a route in the trip planner contract', () => {
    expect(tripPlannerPaths).toContain(pathOf(trailsUrl('https://api.example.com/')))
  })
})

describe('trailSignalUrl', () => {
  it('asks for a route in the trip planner contract', () => {
    const path = pathOf(trailSignalUrl('https://api.example.com', 'grca-bright-angel'))
    expect(path).toBe('/trails/grca-bright-angel/signal')
    expect(tripPlannerPaths).toContain('/trails/{trail_id}/signal')
  })

  it('encodes the trail ID, so it cannot change the address', () => {
    expect(pathOf(trailSignalUrl('https://api.example.com', 'a/b'))).toBe('/trails/a%2Fb/signal')
  })
})

describe('reportsUrl', () => {
  it('posts to the report route in the trip planner contract', () => {
    expect(pathOf(reportsUrl('https://api.example.com/'))).toBe('/reports')
    expect(tripPlannerPaths).toContain('/reports')
  })
})

describe('reportCountsUrl', () => {
  it('asks for the report count route in the trip planner contract', () => {
    expect(pathOf(reportCountsUrl('https://api.example.com/', 'grca-bright-angel'))).toBe(
      '/report-counts',
    )
    expect(tripPlannerPaths).toContain('/report-counts')
  })

  it('puts the trail ID in the query, encoded, so it cannot change the address', () => {
    const url = new URL(reportCountsUrl('https://api.example.com', 'a/b&c=d'))
    expect(url.searchParams.get('trail_id')).toBe('a/b&c=d')
    expect(url.searchParams.size).toBe(1)
  })
})

describe('the site', () => {
  // The tests above only protect addresses built here, so no page may build one by hand.
  const sources = import.meta.glob(['../**/*.{ts,tsx}', '!../**/*.test.ts', '!./api.ts'], {
    query: '?raw',
    import: 'default',
    eager: true,
  }) as Record<string, string>

  it('builds every API address with the functions in lib/api.ts', () => {
    const handBuilt = Object.entries(sources)
      .filter(([, text]) => text.includes('VITE_API_BASE_URL}'))
      .map(([file]) => file)
    expect(handBuilt).toEqual([])
  })

  it('reads the source files it checks', () => {
    expect(Object.keys(sources)).toContain('../pages/Trails.tsx')
  })
})
