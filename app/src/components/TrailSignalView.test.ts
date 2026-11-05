import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import type { PointSignal, TrailSignal } from '../lib/trailSignal'
import { renderMarkup, visibleText } from '../testing/markup'
import { TrailSignalView } from './TrailSignalView'

const point = (seq: number, covered: boolean, windows: PointSignal['windows']): PointSignal => ({
  trail_point_id: `ba-0000${seq}`,
  seq,
  lon: -112.1,
  lat: 36.1,
  coverage: [{ carrier: 'T-Mobile', covered }],
  windows,
})

const manyPoints = (count: number): PointSignal[] =>
  Array.from({ length: count }, (_, seq) => ({ ...point(seq, true, []), lon: -112 + seq / 1000 }))

const passed = { start_utc: '2026-11-05T10:05:00Z', end_utc: '2026-11-05T10:08:00Z' }
const current = { start_utc: '2026-11-05T11:00:00Z', end_utc: '2026-11-05T13:00:00Z' }

const signal: TrailSignal = {
  trail_id: 'grca-bright-angel',
  run_logical_date: '2026-11-05',
  valid_until_utc: '2026-11-06T12:00:00Z',
  last_good_run_utc: '2026-11-05T10:01:00Z',
  min_elevation_deg: 10,
  carriers: ['T-Mobile'],
  points: [point(0, true, [passed, current]), point(1, false, []), point(2, true, [])],
}

const now = new Date('2026-11-05T12:00:00Z')
const late = new Date('2026-11-06T12:30:00Z')

function render(when: Date): string {
  return renderMarkup(createElement(TrailSignalView, { signal, now: when }))
}

const coveredRuns = (markup: string): number =>
  markup.match(/class="trail-run trail-run-covered"/g)?.length ?? 0

describe('TrailSignalView', () => {
  it('shows when the predictions stop being valid', () => {
    expect(visibleText(render(now))).toContain('Predictions valid until')
  })

  it('colors the trail line only where the carrier has coverage', () => {
    expect(coveredRuns(render(now))).toBe(2)
    expect(render(now).match(/class="trail-run trail-run-none"/g)?.length).toBe(1)
  })

  it('has a key that says what every line on the map means', () => {
    const text = visibleText(render(now))
    expect(text).toContain('T-Mobile claims coverage')
    expect(text).toContain('No T-Mobile, but a satellite is reachable now')
    expect(text).toContain('Neither right now')
    expect(text).toContain('You are here')
  })

  it('draws the real terrain under the trail line', () => {
    const known = { ...signal, trail_id: 'grca-bright-angel', points: manyPoints(255) }
    const markup = renderMarkup(createElement(TrailSignalView, { signal: known, now }))
    expect(markup).toContain('href="/trails/grca-bright-angel-terrain.png"')
    expect(markup.indexOf('trail-terrain')).toBeLessThan(markup.indexOf('trail-run'))
  })

  it('shows how the ground rises and falls, and the height at the chosen spot', () => {
    const known = { ...signal, trail_id: 'grca-bright-angel', points: manyPoints(255) }
    const markup = renderMarkup(createElement(TrailSignalView, { signal: known, now }))
    expect(markup).toContain('class="elevation-profile"')
    expect(visibleText(markup)).toMatch(/Elevation about [\d,]+ m \([\d,]+ ft\)/)
  })

  it('shows a photo of the trail with its credit', () => {
    const known = { ...signal, trail_id: 'grca-bright-angel', points: manyPoints(255) }
    const markup = renderMarkup(createElement(TrailSignalView, { signal: known, now }))
    expect(markup).toContain('src="/trails/grca-bright-angel.jpg"')
    expect(visibleText(markup)).toContain('Photo:')
  })

  it('still works for a trail with no terrain or photo', () => {
    const unknown = { ...signal, trail_id: 'no-such-trail' }
    const markup = renderMarkup(createElement(TrailSignalView, { signal: unknown, now }))
    expect(markup).not.toContain('trail-terrain')
    expect(markup).not.toContain('<img')
    expect(markup).not.toContain('elevation-profile')
  })

  it('marks the start and the end of the trail', () => {
    const text = visibleText(render(now))
    expect(text).toContain('Start')
    expect(text).toContain('End')
  })

  it('lets the reader walk the trail', () => {
    expect(visibleText(render(now))).toContain('Walk the trail')
    expect(render(now)).toContain('class="trail-you"')
  })

  it('says in words what the phone and the satellite can do at the chosen spot', () => {
    const text = visibleText(render(now))
    expect(text).toContain('Phone')
    expect(text).toContain('Satellite')
    expect(text).toContain('Reachable now')
  })

  it('leaves the satellite out of the key when the data is late', () => {
    const text = visibleText(render(late))
    expect(text).not.toContain('a satellite is reachable now')
    expect(text).toContain('No coverage claimed')
  })

  it('says how many points have coverage, for readers who cannot see the bars', () => {
    expect(render(now)).toContain('T-Mobile coverage at 2 of 3 points')
  })

  it('shows satellite reach right now along the trail', () => {
    expect(render(now)).toContain('Satellite reachable now at 1 of 3 points')
  })

  it('states that coverage is a claim and satellite texts are not guaranteed', () => {
    expect(visibleText(render(now))).toContain(
      "Coverage shown is the FCC's modelled claim, not a measurement. Satellite texts are not " +
        'guaranteed: they need T-Mobile service and a supported phone, and they can fail under ' +
        'cover that the terrain model does not show.',
    )
  })

  it('lists the first point by default, with its coverage', () => {
    const text = visibleText(render(now))
    expect(text).toContain('T-Mobile: covered')
  })

  it('draws a passed window in grey with a label and never hides it', () => {
    const markup = render(now)
    expect(markup.match(/class="window window-passed"/g)?.length).toBe(1)
    expect(markup.match(/class="window"/g)?.length).toBe(1)
    expect(visibleText(markup)).toContain('passed')
  })

  it('shows no late notice while the data is valid', () => {
    expect(visibleText(render(now))).not.toContain('Data is late')
  })

  it('shows the late notice above the strip map, and keeps the data', () => {
    const markup = render(late)
    expect(visibleText(markup)).toContain('Data is late. Last good run:')
    expect(visibleText(markup)).toContain('Predictions valid until:')
    expect(markup.indexOf('Data is late')).toBeLessThan(markup.indexOf('strip-map'))
    expect(coveredRuns(markup)).toBe(2)
    expect(markup.match(/class="window window-passed"/g)?.length).toBe(2)
  })

  it('does not claim a satellite is reachable now when the data is late', () => {
    expect(render(late)).not.toContain('Satellite reachable now')
  })
})
