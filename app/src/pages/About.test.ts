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

  it('names the report buttons by their words', () => {
    expect(text).toContain('one tap on "Yes, I have signal" or "No signal"')
    expect(text).not.toContain('I had signal here')
    expect(text).not.toContain('I had no signal here')
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

describe('About page, how it is built', () => {
  const markup = renderMarkup(createElement(MemoryRouter, null, createElement(About)))
  const text = visibleText(markup)
  const section = markup.slice(markup.indexOf('id="built-heading"'), markup.indexOf('id="dtc-heading"'))
  const list = section.slice(section.indexOf('<ol'), section.indexOf('</ol>'))
  const listText = visibleText(list)

  it('comes after Behind the scenes and before the Direct-to-Cell note', () => {
    expect(text.indexOf('Behind the scenes')).toBeLessThan(text.indexOf('How it is built'))
    expect(text.indexOf('How it is built')).toBeLessThan(text.indexOf('What Direct-to-Cell needs'))
  })

  it('shows the diagram', () => {
    expect(section).toContain('class="build-diagram"')
  })

  it('lists the five steps in order', () => {
    const steps = ['Public data', 'Nightly job', 'Data lake', 'Checked marts', 'Small web service']
    const positions = steps.map((step) => listText.indexOf(step))
    expect(positions.every((at) => at >= 0)).toBe(true)
    expect([...positions].sort((a, b) => a - b)).toEqual(positions)
  })

  it.each(['Airflow', 'Spark', 'Iceberg', 'S3', 'dbt', 'DuckDB', 'Parquet', 'FastAPI', 'Lambda', 'React', 'CloudFront'])(
    'names %s once in the list of steps',
    (tool) => {
      expect(listText.split(tool)).toHaveLength(2)
    },
  )

  it('spells out each abbreviation the first time it appears', () => {
    expect(listText).toContain("S3, Amazon's Simple Storage Service")
    expect(listText).toContain('dbt (data build tool)')
  })

  it('says the page keeps working while the nightly server is off', () => {
    expect(listText).toContain('even while the nightly server is off')
  })

  it('links to the design documents in the public repository', () => {
    const repo = 'https://github.com/John-Wasikye/will-i-have-signal-out-there/tree/main/docs'
    for (const folder of ['trip-planner', 'platform']) {
      expect(section).toContain(`<a href="${repo}/${folder}" rel="noopener noreferrer">`)
    }
  })

  it('has no number that could go stale', () => {
    expect(visibleText(section)).not.toMatch(/\d{2}/)
  })
})
