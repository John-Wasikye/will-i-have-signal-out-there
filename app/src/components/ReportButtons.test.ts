import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { renderMarkup, visibleText } from '../testing/markup'
import { ReportButtons } from './ReportButtons'

describe('ReportButtons', () => {
  const markup = renderMarkup(createElement(ReportButtons))
  const text = visibleText(markup)

  it('offers both report buttons (FR-49)', () => {
    expect(text).toContain('I had signal here')
    expect(text).toContain('I had no signal here')
    expect(markup.match(/<button/g)).toHaveLength(2)
  })

  it('lets the hiker pick each carrier the API accepts', () => {
    for (const carrier of ['AT&amp;T', 'T-Mobile', 'Verizon']) {
      expect(markup).toContain(`<option value="${carrier}">`)
    }
    expect(markup).toContain('<label')
  })

  it('says the exact position stays on the phone (ADR 0009)', () => {
    expect(text).toContain('Your exact position never leaves your phone')
  })

  it('says a report waits on the phone when there is no signal (ADR 0010)', () => {
    expect(text).toContain('waits on your phone')
  })

  it('says Android sends it by itself and iPhone needs the page open (FR-52)', () => {
    expect(text).toContain('Android sends it by itself when signal returns')
    expect(text).toContain('On iPhone, open this page again')
  })

  it('has a live region for what happened to a report', () => {
    expect(markup).toContain('aria-live="polite"')
  })
})
