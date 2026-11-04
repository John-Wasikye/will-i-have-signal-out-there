import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { renderMarkup, visibleText } from '../testing/markup'
import { Trails } from './Trails'

const comingSoon = 'Coverage and satellite times coming soon'

describe('Trails page', () => {
  const text = visibleText(renderMarkup(createElement(Trails)))

  it('lists the three Phase A trails by name', () => {
    expect(text).toContain('Bright Angel')
    expect(text).toContain('South Kaibab')
    expect(text).toContain('North Kaibab')
  })

  it('marks each trail as coming soon', () => {
    expect(text.split(comingSoon).length - 1).toBe(3)
  })

  it('shows no numbers, bars or times', () => {
    expect(text).not.toMatch(/\d/)
  })

  it('states the Direct-to-Cell requirements and lists the data sources', () => {
    expect(text).toContain('Direct-to-Cell')
    expect(text).toContain('Full credits')
  })
})
