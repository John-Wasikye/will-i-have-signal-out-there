import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import type { Pipeline } from '../lib/status'
import { renderMarkup, visibleText } from '../testing/markup'
import { PipelineCard, PipelineKey } from './PipelineCard'

const pipeline: Pipeline = {
  name: 'platform_skeleton',
  state: 'ok',
  last_good_run_utc: '2026-11-04T10:00:00Z',
  freshness_target_hours: 26,
  last_row_count: 3,
}

function render(item: Pipeline): string {
  return renderMarkup(createElement(PipelineCard, { pipeline: item }))
}

describe('PipelineCard', () => {
  it('uses plain names, not the code name', () => {
    const text = visibleText(render(pipeline))
    expect(text).toContain('Nightly system check')
    expect(text).not.toContain('platform_skeleton')
  })

  it('names the sample pipeline the same plain way', () => {
    expect(visibleText(render({ ...pipeline, name: 'sample_pipeline' }))).toContain('Nightly system check')
  })

  it('tidies a code name it does not know', () => {
    expect(visibleText(render({ ...pipeline, name: 'trail_loader' }))).toContain('Trail loader')
  })

  it('says what the job is for', () => {
    expect(visibleText(render(pipeline))).toContain('proves the nightly system works')
  })

  it.each([
    ['ok', 'Working'],
    ['late', 'Running late'],
    ['failed', 'Failed'],
  ] as const)('labels the state %s as %s', (state, label) => {
    expect(visibleText(render({ ...pipeline, state }))).toContain(label)
  })

  it('says every fact in words', () => {
    const text = visibleText(render(pipeline))
    expect(text).toContain('Last finished')
    expect(text).toContain('Should run at least every 26 hours')
    expect(text).toContain('Test records checked: 3')
  })

  it('copes with a job that has not finished yet', () => {
    const fresh: Pipeline = { name: 'trail_loader', state: 'failed', freshness_target_hours: 26 }
    expect(visibleText(render(fresh))).toContain('No successful run yet')
  })

  it('links to an incident only when the address is safe', () => {
    const safe = render({ ...pipeline, incident_url: 'https://example.test/1' })
    expect(safe).toContain('Open incident')
    const unsafe = render({ ...pipeline, incident_url: 'javascript:alert(1)' })
    expect(unsafe).not.toContain('Open incident')
  })
})

describe('PipelineKey', () => {
  it('explains every state', () => {
    const text = visibleText(renderMarkup(createElement(PipelineKey)))
    expect(text).toContain('Working')
    expect(text).toContain('Running late')
    expect(text).toContain('Failed')
    expect(text).toContain('the site keeps showing the last good data')
  })
})
