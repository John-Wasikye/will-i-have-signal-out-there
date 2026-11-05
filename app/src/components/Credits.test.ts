import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { renderMarkup, visibleText } from '../testing/markup'
import { Credits } from './Credits'

describe('Credits', () => {
  it('credits each data source', () => {
    const text = visibleText(renderMarkup(createElement(Credits)))
    expect(text).toContain('CelesTrak')
    expect(text).toContain('National Park Service')
    expect(text).toContain('FCC National Broadband Map')
    expect(text).toContain('Copernicus')
  })

  it('gives the exact Copernicus notice for modified data', () => {
    const text = visibleText(renderMarkup(createElement(Credits)))
    expect(text).toContain('produced using Copernicus WorldDEM-30')
    expect(text).toContain('all rights reserved.')
  })

  it('no longer says the credits are still to come', () => {
    const text = visibleText(renderMarkup(createElement(Credits)))
    expect(text).not.toContain('will draw on')
    expect(text).not.toContain('come with the live data')
  })
})
