import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { renderMarkup } from '../testing/markup'
import { BuildDiagram } from './BuildDiagram'

describe('BuildDiagram', () => {
  const markup = renderMarkup(createElement(BuildDiagram))
  const label = markup.match(/aria-label="([^"]*)"/)?.[1] ?? ''

  it('is one image with a text alternative, not a set of loose shapes', () => {
    expect(markup).toMatch(/^<svg [^>]*role="img"/)
    expect(label.length).toBeGreaterThan(80)
  })

  it('says in words what it shows, in the order of the boxes', () => {
    const steps = [
      'public data (orbits, trails, coverage, terrain)',
      'the nightly job (Airflow, Spark)',
      'the data lake (Iceberg tables on S3)',
      'checked marts (dbt, DuckDB) and a publish gate',
      'a small web service and this page',
    ]
    const positions = steps.map((step) => label.indexOf(step))
    expect(positions.every((at) => at >= 0)).toBe(true)
    expect([...positions].sort((a, b) => a - b)).toEqual(positions)
  })

  it('draws five boxes with an arrow between each pair', () => {
    expect(markup.match(/class="diagram-box"/g)).toHaveLength(5)
    expect(markup.match(/class="diagram-arrow"/g)).toHaveLength(4)
  })

  it('names each box on the picture', () => {
    for (const title of [
      'Public data',
      'Nightly job',
      'Data lake',
      'Checked marts and a publish gate',
      'Small web service and this page',
    ]) {
      expect(markup).toContain(title)
    }
  })

  it('is styled by classes only, with no inline style and nothing that scales past the page', () => {
    expect(markup).not.toContain('style=')
    expect(markup).toContain('viewBox=')
    expect(markup).not.toMatch(/<svg [^>]*\swidth=/)
  })
})
