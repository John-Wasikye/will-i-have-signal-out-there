import { createElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect } from 'vitest'
import App from './App'
import { renderMarkup, visibleText } from './testing/markup'

function renderPage(path: string): string {
  return renderMarkup(createElement(MemoryRouter, { initialEntries: [path] }, createElement(App)))
}

const pages = ['/', '/trails', '/about', '/lookup', '/status', '/no-such-page']

describe('the development banner', () => {
  it.each(pages)('is gone from %s, because the footer carries the safety note', (path) => {
    const markup = renderPage(path)
    expect(markup).not.toContain('dev-banner')
    expect(visibleText(markup)).not.toContain('Under development')
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
  it('links to the trails, how it works and status pages', () => {
    const text = visibleText(renderPage('/').split('</header>')[0])
    expect(text).toContain('Trails')
    expect(text).toContain('How it works')
    expect(text).toContain('Status')
  })

  it('leaves out the lookup page, which is a developer sample', () => {
    expect(renderPage('/')).not.toContain('href="/lookup"')
  })
})

describe('the site footer', () => {
  it.each(pages)('follows the main part of the page on %s', (path) => {
    const markup = renderPage(path)
    expect(markup.indexOf('<footer')).toBeGreaterThan(markup.indexOf('</main>'))
  })

  it.each(pages)('says it is a portfolio project and not to rely on it for safety on %s', (path) => {
    const footer = visibleText(renderPage(path).split('<footer')[1] ?? '')
    expect(footer).toContain('I built this site as a portfolio project.')
    expect(footer).toContain(
      'I have not checked its predictions in the field, so do not rely on it for your safety.',
    )
  })

  it.each(pages)('links to how it works, status, the credits and the source code on %s', (path) => {
    const footer = renderPage(path).split('<footer')[1] ?? ''
    expect(footer).toMatch(/<a href="\/about"[^>]*>How it works<\/a>/)
    expect(footer).toMatch(/<a href="\/status"[^>]*>Status<\/a>/)
    expect(footer).toMatch(/<a href="\/about#credits-heading"[^>]*>Data sources and credits<\/a>/)
    expect(footer).toMatch(
      /<a href="https:\/\/github\.com\/John-Wasikye\/will-i-have-signal-out-there" rel="noopener noreferrer">Source code on GitHub<\/a>/,
    )
  })

  it('has a credits heading on the About page for the footer link to reach', () => {
    expect(renderPage('/about')).toContain('id="credits-heading"')
  })
})

describe('routes', () => {
  it('shows a page not found page with a way back, not a bare heading', () => {
    const markup = renderPage('/no-such-page')
    expect(visibleText(markup)).toContain('I could not find that page.')
    expect(markup).toContain('<h1>Page not found</h1>')
  })

  it('makes the trail tool the home page', () => {
    const text = visibleText(renderPage('/'))
    expect(text).toContain('Choose a trail')
    expect(text).not.toContain('Page not found')
  })

  it('opens with a big title only on the trail tool', () => {
    expect(renderPage('/')).toContain('class="hero"')
    expect(renderPage('/trails')).toContain('class="hero"')
    expect(renderPage('/about')).not.toContain('class="hero"')
  })

  it('moves the explanation to /about', () => {
    const text = visibleText(renderPage('/about'))
    expect(text).toContain('How it works')
    expect(text).toContain('What it covers today')
    expect(text).not.toContain('Page not found')
  })

  it('serves the trails page at /trails', () => {
    const text = visibleText(renderPage('/trails'))
    expect(text).toContain('Walk a trail before you go')
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
  it.each(pages)('never uses the word Phase on %s', (path) => {
    expect(visibleText(renderPage(path))).not.toContain('Phase')
  })

  it.each(pages)('uses no em dash, en dash or spaced hyphen on %s', (path) => {
    const text = visibleText(renderPage(path))
    expect(text).not.toContain('—')
    expect(text).not.toContain('–')
    expect(text).not.toContain(' - ')
  })
})
