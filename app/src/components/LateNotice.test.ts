import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { renderMarkup, visibleText } from '../testing/markup'
import { LateNotice } from './LateNotice'

function render(pipelineName: string): string {
  return visibleText(
    renderMarkup(
      createElement(LateNotice, { pipelineName, lastGoodRunUtc: '2026-11-04T10:00:00Z' }),
    ),
  )
}

describe('LateNotice', () => {
  it('uses the plain title the pipeline card shows, not the code name', () => {
    const text = render('platform_skeleton')
    expect(text).toContain('Nightly system check is late or has failed.')
    expect(text).not.toContain('platform_skeleton')
  })

  it('tidies the name of a pipeline it does not know', () => {
    expect(render('trail_loader')).toContain('Trail loader is late or has failed.')
  })

  it('says when no good run has finished yet', () => {
    const text = visibleText(
      renderMarkup(createElement(LateNotice, { pipelineName: 'trail_loader' })),
    )
    expect(text).toContain('No good run has finished yet.')
  })
})
