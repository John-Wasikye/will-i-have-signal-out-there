import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { renderMarkup, visibleText } from '../testing/markup'
import { TrailPlaceholder } from './TrailPlaceholder'

describe('TrailPlaceholder', () => {
  const markup = renderMarkup(createElement(TrailPlaceholder))

  it('is a block that holds the place of the trail view', () => {
    expect(markup).toContain('class="trail-placeholder"')
  })

  it('holds the cold start notice, so the wait is explained where the map will be', () => {
    expect(visibleText(markup)).toContain('may take up to 10 seconds')
    expect(markup.match(/role="status"/g)).toHaveLength(1)
  })
})
