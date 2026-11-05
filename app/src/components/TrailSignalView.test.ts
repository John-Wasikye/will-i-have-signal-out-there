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

const stripBars = (markup: string): number => markup.match(/class="strip-bar"/g)?.length ?? 0

describe('TrailSignalView', () => {
  it('shows when the predictions stop being valid', () => {
    expect(visibleText(render(now))).toContain('Predictions valid until')
  })

  it('draws a coverage bar only where the carrier has coverage', () => {
    expect(stripBars(render(now))).toBe(2)
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
    expect(stripBars(markup)).toBe(2)
    expect(markup.match(/class="window window-passed"/g)?.length).toBe(2)
  })

  it('does not claim a satellite is reachable now when the data is late', () => {
    expect(render(late)).not.toContain('Satellite reachable now')
  })
})
