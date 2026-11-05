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
    expect(text).toContain('about 12 more hours')
  })

  it('draws how much time the predictions have left', () => {
    expect(render('2026-11-05T12:00:00Z')).toContain('<meter')
  })

  it('says when the next run is', () => {
    expect(visibleText(render('2026-11-05T12:00:00Z'))).toContain('every night at 10:00 UTC')
  })

  it('says less than an hour near the end', () => {
    expect(visibleText(render('2026-11-05T23:40:00Z'))).toContain('less than an hour')
  })

  it('shows the late notice with the last good run once the time has passed', () => {
    const text = visibleText(render('2026-11-06T02:00:00Z'))
    expect(text).toContain('Data is late')
    expect(text).toContain('Last good run')
    expect(text).not.toContain('Up to date')
  })
})
