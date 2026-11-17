import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import type { Pipeline } from '../lib/status'
import { renderMarkup, visibleText } from '../testing/markup'
import type { PredictionsCard as PredictionsCardState } from '../lib/trailPredictions'
import { PipelineCard, PipelineKey, PredictionsCard } from './PipelineCard'

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
    expect(text).toContain('Every night. Counted as late after 26 hours.')
  })

  it('does not show the number of test records', () => {
    expect(visibleText(render(pipeline))).not.toContain('Test records checked')
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

describe('PredictionsCard', () => {
  const ready = (state: 'ok' | 'late'): PredictionsCardState => ({
    kind: 'ready',
    state,
    lastGoodRunUtc: '2026-11-05T10:01:00Z',
    validUntilUtc: '2026-11-06T12:00:00Z',
  })
  const render = (card: PredictionsCardState): string =>
    visibleText(renderMarkup(createElement(PredictionsCard, { card })))

  it('has a title and says what the job is for', () => {
    const text = render(ready('ok'))
    expect(text).toContain('Trail predictions')
    expect(text).toContain(
      'The nightly job that works out coverage and satellite windows for every trail.',
    )
  })

  it('shows Working when the predictions are valid and Running late when they are not', () => {
    expect(render(ready('ok'))).toContain('Working')
    expect(render(ready('late'))).toContain('Running late')
    expect(render(ready('late'))).not.toContain('Working')
  })

  it('never shows the Failed state', () => {
    expect(render(ready('ok'))).not.toContain('Failed')
    expect(render(ready('late'))).not.toContain('Failed')
  })

  it('gives the last finished and valid until times and the schedule', () => {
    const text = render(ready('ok'))
    expect(text).toMatch(/Last finished Nov \d+, 2026, \d{1,2}:\d{2} [AP]M \S+/)
    expect(text).toMatch(/Valid until Nov \d+, 2026, \d{1,2}:\d{2} [AP]M \S+/)
    expect(text).toContain('Schedule Every night at 10:00 UTC.')
  })

  it('uses the same card and badge styles as the other pipelines', () => {
    const markup = renderMarkup(createElement(PredictionsCard, { card: ready('ok') }))
    expect(markup).toContain('<li class="card">')
    expect(markup).toContain('class="state-badge state-ok"')
  })

  it('says in words that it is loading, with no state', () => {
    const text = render({ kind: 'loading' })
    expect(text).toContain('Loading the trail predictions.')
    expect(text).not.toContain('Working')
    expect(text).not.toContain('Running late')
  })

  it('says in words that the trail data is unavailable, with no state', () => {
    const text = render({ kind: 'error' })
    expect(text).toContain('The trail predictions are unavailable right now.')
    expect(text).not.toContain('Working')
  })
})
