import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { renderMarkup } from '../testing/markup'
import { MountainBackdrop } from './MountainBackdrop'

describe('MountainBackdrop', () => {
  const markup = renderMarkup(createElement(MountainBackdrop))

  it('draws ridgelines from far to near, then the ground the page sits on', () => {
    const order = ['ridge-far', 'ridge-mid', 'ridge-near', 'ridge-ground'].map((name) =>
      markup.indexOf(name),
    )
    expect(order.every((at) => at >= 0)).toBe(true)
    expect(order).toEqual([...order].sort((a, b) => a - b))
  })

  it('is decoration, so screen readers skip it', () => {
    expect(markup).toContain('aria-hidden="true"')
  })

  it('fills any screen width without stretching the peaks', () => {
    expect(markup).toContain('preserveAspectRatio="xMidYMax slice"')
  })
})
