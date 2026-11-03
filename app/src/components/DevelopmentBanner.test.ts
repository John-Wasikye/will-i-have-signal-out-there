import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { renderMarkup, visibleText } from '../testing/markup'
import { DevelopmentBanner } from './DevelopmentBanner'

describe('DevelopmentBanner', () => {
  it('announces in a status region that the site does not show real data yet', () => {
    const markup = renderMarkup(createElement(DevelopmentBanner))
    expect(markup).toContain('role="status"')
    expect(visibleText(markup)).toContain(
      'Under development: this site does not show real coverage or satellite times yet.',
    )
  })

  it('says the data pipeline is still being built', () => {
    const text = visibleText(renderMarkup(createElement(DevelopmentBanner)))
    expect(text).toContain('The data pipeline')
    expect(text).toContain('still being built')
  })
})
