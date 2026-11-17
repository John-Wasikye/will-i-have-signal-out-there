import { createElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect } from 'vitest'
import { renderMarkup, visibleText } from '../testing/markup'
import { NotFound } from './NotFound'

describe('NotFound page', () => {
  const markup = renderMarkup(createElement(MemoryRouter, null, createElement(NotFound)))

  it('has a heading and one sentence that says what happened', () => {
    expect(markup).toContain('<h1>Page not found</h1>')
    expect(visibleText(markup)).toContain('I could not find that page.')
  })

  it('links back to the trails', () => {
    expect(markup).toMatch(/<a href="\/"[^>]*>[^<]*trails[^<]*<\/a>/i)
  })
})
