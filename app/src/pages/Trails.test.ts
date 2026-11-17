import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { renderMarkup, visibleText } from '../testing/markup'
import { Trails } from './Trails'

describe('Trails page', () => {
  const text = visibleText(renderMarkup(createElement(Trails)))

  it('introduces the tool directly under the heading', () => {
    expect(text).toContain(
      'Walk a trail before you go Choose a trail, pick your carrier, and press "Walk the trail".',
    )
    expect(text).toContain('on T-Mobile, when a satellite text could get through')
  })

  it('spells out FCC where the page first mentions it', () => {
    expect(text).toContain('Federal Communications Commission (FCC)')
    expect(text.indexOf('FCC')).toBe(text.indexOf('(FCC)') + 1)
  })

  it('no longer ends with the old paragraph about T-Mobile coverage', () => {
    expect(text).not.toContain('I cover three main trails')
    expect(text).not.toContain('where T-Mobile claims coverage and where a satellite')
  })

  it('no longer says the data is coming soon', () => {
    expect(text).not.toContain('coming soon')
    expect(text).not.toContain('not ready yet')
  })

  it('asks the reader to pick a trail', () => {
    expect(text).toContain('Choose a trail')
  })

  it('states the Direct-to-Cell requirements and credits the data sources', () => {
    expect(text).toContain('Direct-to-Cell')
    expect(text).toContain('Trail data: National Park Service.')
  })

  it('offers the trail map before any choice, so there is something to try at once', () => {
    expect(text).toContain('Walk')
  })

  it('lets a hiker report signal from the trail page (FR-49)', () => {
    expect(text).toContain('I had signal here')
    expect(text).toContain('I had no signal here')
  })

  it('shows the cold start notice', () => {
    expect(text).toContain('may take up to 10 seconds')
  })
})
