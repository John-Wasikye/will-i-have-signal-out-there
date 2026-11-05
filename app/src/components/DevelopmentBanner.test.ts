import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { renderMarkup, visibleText } from '../testing/markup'
import { DevelopmentBanner } from './DevelopmentBanner'

describe('DevelopmentBanner', () => {
  it('announces in a status region that the site is still being built', () => {
    const markup = renderMarkup(createElement(DevelopmentBanner))
    expect(markup).toContain('role="status"')
    expect(visibleText(markup)).toContain('Under development:')
  })

  it('warns not to rely on it for safety', () => {
    const text = visibleText(renderMarkup(createElement(DevelopmentBanner)))
    expect(text).toContain('Do not rely on it for your safety')
  })

  it('no longer says the site has no real data', () => {
    const text = visibleText(renderMarkup(createElement(DevelopmentBanner)))
    expect(text).not.toContain('does not show real')
  })
})
