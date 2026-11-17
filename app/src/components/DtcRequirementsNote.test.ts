import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { renderMarkup, visibleText } from '../testing/markup'
import { DtcRequirementsNote } from './DtcRequirementsNote'

describe('DtcRequirementsNote', () => {
  const text = visibleText(renderMarkup(createElement(DtcRequirementsNote)))

  it('says Direct-to-Cell texting needs T-Mobile service in the United States', () => {
    expect(text).toContain('Direct-to-Cell')
    expect(text).toContain('needs T-Mobile service in the United States')
  })

  it('says a supported phone is also needed', () => {
    expect(text).toContain('a supported phone')
  })

  it('says the map shows satellite reach only when T-Mobile is the chosen carrier', () => {
    expect(text).toContain('shows satellite reach only when T-Mobile is the chosen carrier')
    expect(text).not.toContain('Phase')
  })

  it('says satellite texts are not guaranteed and coverage maps are a carrier claim', () => {
    expect(text).toContain('Satellite texts are not guaranteed')
    expect(text).toContain("Coverage maps are a carrier's own claim")
  })
})
