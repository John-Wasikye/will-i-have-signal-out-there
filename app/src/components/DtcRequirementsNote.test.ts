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

  it('says a supported phone is also needed and that T-Mobile is the Phase A carrier', () => {
    expect(text).toContain('a supported phone')
    expect(text).toContain('T-Mobile is the carrier for Phase A')
  })

  it('says satellite texts are not guaranteed and coverage maps are a carrier claim', () => {
    expect(text).toContain('Satellite texts are not guaranteed')
    expect(text).toContain("Coverage maps are a carrier's own claim")
  })
})
