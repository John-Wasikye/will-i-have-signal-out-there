import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { renderMarkup } from '../testing/markup'
import { Logo } from './Logo'

describe('Logo', () => {
  const markup = renderMarkup(createElement(Logo))

  it('draws the outline of a person and a hiking stick', () => {
    expect(markup).toContain('class="logo-hiker"')
    expect(markup).toContain('class="logo-stick"')
  })

  it('stays out of the way of screen readers, because the site name sits beside it', () => {
    expect(markup).toContain('aria-hidden="true"')
  })

  it('uses no inline style, which the site security policy would block', () => {
    expect(markup).not.toContain('style=')
  })
})
