import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import type { ReportCount } from '../lib/reportCounts'
import { renderMarkup, visibleText } from '../testing/markup'
import { ReportCounts } from './ReportCounts'

function render(counts: ReportCount[] | null, failed = false): string {
  return visibleText(renderMarkup(createElement(ReportCounts, { counts, failed })))
}

describe('ReportCounts', () => {
  it('says there are too few reports when no area along the trail has 5 (ADR 0030)', () => {
    const text = render([])
    expect(text).toContain('Hiker reports along this trail, last 7 days')
    expect(text).toContain('Too few reports to show.')
  })

  it('shows each carrier with how many hikers had signal and how many had none', () => {
    const text = render([
      { area_id: 'a', carrier: 'T-Mobile', had_signal: true, report_count: 4 },
      { area_id: 'a', carrier: 'T-Mobile', had_signal: false, report_count: 1 },
    ])
    expect(text).toContain('T-Mobile: 4 had signal, 1 had no signal')
    expect(text).not.toContain('Too few reports')
  })

  it('says the counts are hikers own reports, not checked', () => {
    expect(render([])).toContain('not checked')
  })

  it('says so when the counts could not be loaded', () => {
    expect(render(null, true)).toContain('Hiker reports could not be loaded.')
  })

  it('shows nothing while the counts are loading', () => {
    expect(render(null)).toBe('')
  })
})
