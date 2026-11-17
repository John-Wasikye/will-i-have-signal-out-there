import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { renderMarkup, visibleText } from '../testing/markup'
import { DataFreshness } from './DataFreshness'

const props = {
  lastGoodRunUtc: '2026-11-05T00:00:00Z',
  validUntilUtc: '2026-11-06T00:00:00Z',
}

function render(now: string): string {
  return renderMarkup(createElement(DataFreshness, { ...props, now: new Date(now) }))
}

describe('DataFreshness', () => {
  it('says in plain words that the data is fresh and for how long', () => {
    const text = visibleText(render('2026-11-05T12:00:00Z'))
    expect(text).toContain('Up to date')
    expect(text).toContain('The trail predictions are good for another 12 hours.')
  })

  it('shows the exact time left in hours and minutes, never "about"', () => {
    const text = visibleText(render('2026-11-05T16:07:30Z'))
    expect(text).toContain('The trail predictions are good for another 7 hours 52 minutes.')
    expect(text).not.toContain('about')
  })

  it('draws how much time the predictions have left', () => {
    expect(render('2026-11-05T12:00:00Z')).toContain('<meter')
  })

  it('says when the next run is', () => {
    expect(visibleText(render('2026-11-05T12:00:00Z'))).toContain(
      'Every night at 10:00 UTC (Coordinated Universal Time).',
    )
  })

  it('gives the next run in the local time of the reader, with the zone name', () => {
    // 10:00 UTC on Nov 6 is Nov 6 in every zone from UTC-10 to UTC+13, and Nov 5 further west.
    expect(visibleText(render('2026-11-05T12:00:00Z'))).toMatch(
      /The next one is Nov [56], 2026, \d{1,2}:00 [AP]M \S+\./,
    )
  })

  it('moves the next run to the following day at exactly 10:00 UTC', () => {
    const before = visibleText(render('2026-11-05T09:59:00Z'))
    const at = visibleText(render('2026-11-05T10:00:00Z'))
    expect(before).not.toEqual(at)
  })

  it('says the minutes near the end and less than a minute at the very end', () => {
    expect(visibleText(render('2026-11-05T23:40:00Z'))).toContain('good for another 20 minutes.')
    expect(visibleText(render('2026-11-05T23:59:30Z'))).toContain('good for less than a minute.')
  })

  it('shows the late notice with the last good run once the time has passed', () => {
    const text = visibleText(render('2026-11-06T02:00:00Z'))
    expect(text).toContain('Data is late')
    expect(text).toContain('Last good run')
    expect(text).not.toContain('Up to date')
  })
})
