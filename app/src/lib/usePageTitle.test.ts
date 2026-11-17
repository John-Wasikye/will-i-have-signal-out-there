import { describe, it, expect } from 'vitest'
import { pageTitle } from './usePageTitle'

describe('pageTitle', () => {
  it.each(['Trails', 'How it works', 'Status', 'Page not found'])('puts the site name after "%s"', (name) => {
    expect(pageTitle(name)).toBe(`${name} | Will I have signal out there?`)
  })
})
