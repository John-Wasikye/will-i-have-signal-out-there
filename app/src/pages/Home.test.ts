import { createElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect } from 'vitest'
import { renderMarkup, visibleText } from '../testing/markup'
import { Home } from './Home'

describe('Home page', () => {
  // The page has router links, so it renders inside a router as it does in the app.
  const text = visibleText(renderMarkup(createElement(MemoryRouter, null, createElement(Home))))

  it('no longer says the planner shows no data', () => {
    expect(text).not.toContain('does not show any coverage')
    expect(text).not.toContain('Once the data pipeline is finished')
  })

  it('describes what the planner does', () => {
    expect(text).toContain('coverage bars along a trail')
    expect(text).toContain('canyon walls')
    expect(text).toContain('Predictions valid until')
  })

  it('states the Phase A scope: main trails, T-Mobile, the next 24 hours', () => {
    expect(text).toContain('Phase A')
    expect(text).toContain('Bright Angel, South Kaibab and North Kaibab')
    expect(text).toContain('T-Mobile')
    expect(text).toContain('next 24 hours')
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
