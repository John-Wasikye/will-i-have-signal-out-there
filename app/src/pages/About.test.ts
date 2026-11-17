import { createElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect } from 'vitest'
import { renderMarkup, visibleText } from '../testing/markup'
import { About } from './About'

describe('About page', () => {
  // The page has router links, so it renders inside a router as it does in the app.
  const text = visibleText(renderMarkup(createElement(MemoryRouter, null, createElement(About))))

  it('no longer says the planner shows no data', () => {
    expect(text).not.toContain('does not show any coverage')
    expect(text).not.toContain('Once the data pipeline is finished')
  })

  it('describes what the planner does', () => {
    expect(text).toContain('colors each stretch of a trail')
    expect(text).toContain('canyon walls')
    expect(text).toContain('Predictions valid until')
  })

  it('says what it covers today: trails, carriers, satellite, the next 24 hours, reports', () => {
    expect(text).toContain('What it covers today')
    expect(text).toContain('Bright Angel, South Kaibab and North Kaibab')
    expect(text).toContain('AT&T, T-Mobile and Verizon, on 4G LTE')
    expect(text).toContain('next 24 hours, refreshed every night')
  })

  it('names all three carriers in the opening and in the map bullet', () => {
    expect(text).toContain('where AT&T, T-Mobile and Verizon claim coverage along a trail')
    expect(text).toContain('A carrier picker above the map')
    expect(text).not.toContain('One carrier')
  })

  it('says satellite texting needs T-Mobile', () => {
    expect(text).toContain('Satellite texting needs T-Mobile')
  })

  it('explains hiker reports and what leaves the phone', () => {
    expect(text).toContain('Hiker reports')
    expect(text).toContain('Only an area about 350 m (1,150 ft) across')
    expect(text).toContain('at least 5 reports in 7 days')
  })

  it('looks ahead without promising dates', () => {
    expect(text).toContain('Still to come')
    expect(text).toContain('more places than Grand Canyon')
    expect(text).toContain('confidence rating')
  })

  it('never uses the word Phase', () => {
    expect(text).not.toContain('Phase')
  })

  it('explains the nightly run and that the page works with the nightly machine off', () => {
    expect(text).toContain('10:00 UTC')
    expect(text).toContain('Coordinated Universal Time')
    expect(text).toContain('web service')
    expect(text).toContain('keeps working without it')
  })

  it('shows the Direct-to-Cell requirements and the credits', () => {
    expect(text).toContain('needs T-Mobile service in the United States')
    expect(text).toContain('CelesTrak')
  })
})
