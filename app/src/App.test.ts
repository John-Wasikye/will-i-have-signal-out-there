import { createElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect } from 'vitest'
import App from './App'
import { renderMarkup, visibleText } from './testing/markup'

function renderPage(path: string): string {
  return renderMarkup(createElement(MemoryRouter, { initialEntries: [path] }, createElement(App)))
}

const pages = ['/', '/trails', '/lookup', '/status', '/no-such-page']

describe('the development banner', () => {
  it.each(pages)('is shown above the navigation on %s', (path) => {
    const markup = renderPage(path)
    const bannerAt = markup.indexOf('Under development:')
    expect(bannerAt).toBeGreaterThanOrEqual(0)
    expect(bannerAt).toBeLessThan(markup.indexOf('<header'))
  })
})

describe('the site header', () => {
  it.each(pages)('shows the logo and site name as a link home on %s', (path) => {
    const header = renderPage(path).split('</header>')[0]
    expect(header).toMatch(/<a [^>]*class="brand[^>]*href="\/"|<a [^>]*href="\/"[^>]*class="brand/)
    expect(header).toContain('logo-hiker')
    expect(visibleText(header)).toContain('Will I have signal out there?')
  })

  it.each(pages)('draws the mountain ridgelines on %s', (path) => {
    expect(renderPage(path).split('</header>')[0]).toContain('ridge-far')
  })
})

describe('the navigation', () => {
  it('links to the new trails page', () => {
    expect(renderPage('/')).toContain('href="/trails"')
  })
})

describe('routes', () => {
  it('serves the trails page at /trails', () => {
    const text = visibleText(renderPage('/trails'))
    expect(text).toContain('Bright Angel')
    expect(text).not.toContain('Page not found')
  })

  it('keeps the lookup page working', () => {
    const text = visibleText(renderPage('/lookup'))
    expect(text).toContain('Enter a sample key')
    expect(text).not.toContain('Page not found')
  })

  it('keeps the status page working', () => {
    const text = visibleText(renderPage('/status'))
    expect(text).toContain('Pipeline status')
    expect(text).not.toContain('Page not found')
  })
})

describe('visible text on every page', () => {
  it.each(pages)('uses no em dash, en dash or spaced hyphen on %s', (path) => {
    const text = visibleText(renderPage(path))
    expect(text).not.toContain('—')
    expect(text).not.toContain('–')
    expect(text).not.toContain(' - ')
  })
})
