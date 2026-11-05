import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { renderMarkup, visibleText } from '../testing/markup'
import { Trails } from './Trails'

describe('Trails page', () => {
  const text = visibleText(renderMarkup(createElement(Trails)))

  it('lists the three Phase A trails by name', () => {
    expect(text).toContain('Bright Angel')
    expect(text).toContain('South Kaibab')
    expect(text).toContain('North Kaibab')
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

  it('shows the cold start notice', () => {
    expect(text).toContain('may take up to 10 seconds')
  })
})
