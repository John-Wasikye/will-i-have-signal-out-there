import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { renderMarkup, visibleText } from '../testing/markup'
import { Status } from './Status'

describe('Status page', () => {
  const markup = renderMarkup(createElement(Status))
  const text = visibleText(markup)

  it('lists the trail predictions as the first pipeline card, before status.json has loaded', () => {
    expect(text).toContain('Pipeline status')
    const firstCard = markup.slice(markup.indexOf('<ul class="cards">'))
    expect(visibleText(firstCard.slice(0, firstCard.indexOf('</li>')))).toContain('Trail predictions')
  })

  it('says the predictions are loading while the trail answer is on its way', () => {
    expect(text).toContain('Loading the trail predictions.')
  })

  it('keeps the freshness box and the cold start notice at the top', () => {
    expect(text.indexOf('Can I trust the data right now?')).toBeLessThan(text.indexOf('Pipeline status'))
    expect(text).toContain('may take up to 10 seconds')
  })
})
