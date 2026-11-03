import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { renderMarkup, visibleText } from '../testing/markup'
import { Credits } from './Credits'

describe('Credits', () => {
  it('names each planned data source', () => {
    const text = visibleText(renderMarkup(createElement(Credits)))
    expect(text).toContain('CelesTrak')
    expect(text).toContain('National Park Service')
    expect(text).toContain('Federal Communications Commission (FCC)')
    expect(text).toContain('Copernicus')
  })

  it('says full credits come with the live data', () => {
    const text = visibleText(renderMarkup(createElement(Credits)))
    expect(text).toContain('Full credits')
    expect(text).toContain('live data')
  })
})
