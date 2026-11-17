import { createElement } from 'react'
import { afterEach, describe, it, expect, vi } from 'vitest'
import { renderMarkup } from '../testing/markup'
import { useNow } from './useNow'

function Clock() {
  return createElement('p', null, useNow().toISOString())
}

describe('useNow', () => {
  afterEach(() => vi.useRealTimers())

  // The one-minute timer starts in an effect, which a static render never runs, and the tests
  // have no DOM. The timer is the same code that Trails.tsx used before it moved here.
  it('starts at the current time', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-16T12:34:56Z'))
    expect(renderMarkup(createElement(Clock))).toContain('2026-11-16T12:34:56.000Z')
  })
})
