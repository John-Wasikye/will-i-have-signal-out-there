import { describe, it, expect } from 'vitest'
import indexHtml from '../index.html?raw'
import css from './styles.css?raw'

type Tokens = Record<string, string>

function tokensIn(block: string): Tokens {
  return Object.fromEntries(
    [...block.matchAll(/--(color-[\w-]+):\s*(#[0-9a-f]{6})/g)].map((match) => [match[1], match[2]]),
  )
}

const light = tokensIn(css.slice(0, css.indexOf('@media (prefers-color-scheme: dark)')))
const dark = tokensIn(css.slice(css.indexOf('@media (prefers-color-scheme: dark)')))

function channels(hex: string): number[] {
  return [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16) / 255)
}

function luminance(hex: string): number {
  const [r, g, b] = channels(hex).map((value) =>
    value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4,
  )
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(first: string, second: string): number {
  const [high, low] = [luminance(first), luminance(second)].sort((a, b) => b - a)
  return (high + 0.05) / (low + 0.05)
}

function saturation(hex: string): number {
  const values = channels(hex)
  const [high, low] = [Math.max(...values), Math.min(...values)]
  return high === 0 ? 0 : (high - low) / high
}

const readablePairs = [
  ['color-text', 'color-bg'],
  ['color-text', 'color-card'],
  ['color-text', 'color-sky-top'],
  ['color-text', 'color-sky-bottom'],
  ['color-muted', 'color-bg'],
  ['color-muted', 'color-card'],
  ['color-accent', 'color-bg'],
  ['color-accent', 'color-card'],
  ['color-on-accent', 'color-accent'],
  ['color-error', 'color-bg'],
  ['color-text', 'color-notice-bg'],
  ['color-passed', 'color-card'],
  ['color-on-accent', 'color-coverage'],
  ['color-on-accent', 'color-error'],
  ['color-error', 'color-card'],
]

describe.each([
  ['light', light],
  ['dark', dark],
])('the %s colors', (_name, tokens) => {
  it.each(readablePairs)('keep %s readable on %s', (text, background) => {
    expect(tokens[text]).toBeDefined()
    expect(tokens[background]).toBeDefined()
    expect(contrast(tokens[text], tokens[background])).toBeGreaterThanOrEqual(4.5)
  })

  it('keep passed windows grey', () => {
    expect(saturation(tokens['color-passed'])).toBeLessThan(0.12)
  })

  it('are earthy: the page background is warm, with clearly more red than blue', () => {
    const [red, , blue] = channels(tokens['color-bg'])
    expect(red - blue).toBeGreaterThan(0.02)
  })
})

describe('the color modes', () => {
  it('gives every light color a dark partner', () => {
    expect(Object.keys(dark).sort()).toEqual(Object.keys(light).sort())
  })
})

describe('the site footer', () => {
  const rules = (css.match(/\.(?:site-footer|footer-links)[^{]*\{[^}]*\}/g) ?? []).join('\n')

  it('is styled in the stylesheet', () => {
    expect(rules).not.toBe('')
  })

  it('takes every color from the color variables, so both color modes work', () => {
    expect(rules).not.toMatch(/#[0-9a-f]{3,6}\b/i)
  })

  it('lets the links wrap on a narrow phone', () => {
    expect(rules).toContain('flex-wrap: wrap')
  })
})

describe('the report buttons', () => {
  // The first rule that starts with this selector, up to its closing brace.
  function rule(selector: string): string {
    const start = css.indexOf(`${selector} {`)
    return start < 0 ? '' : css.slice(start, css.indexOf('}', start))
  }

  it.each(['.report-button', '.report-yes', '.report-no', '.report-help summary'])(
    'styles %s',
    (selector) => {
      expect(rule(selector)).not.toBe('')
    },
  )

  it('makes each button at least 44 px high', () => {
    const height = rule('.report-button').match(/min-height:\s*(\d+)px/)?.[1]
    expect(Number(height)).toBeGreaterThanOrEqual(44)
  })

  it('fills the yes button with the coverage green and outlines the no button in the error red', () => {
    expect(rule('.report-yes')).toContain('background: var(--color-coverage)')
    expect(rule('.report-no')).toContain('border-color: var(--color-error)')
  })

  it('takes no height or margin while the status line is empty, but stays in the page', () => {
    expect(rule('.report-status')).not.toContain('min-height')
    expect(rule('.report-status:empty')).toContain('margin: 0')
    expect(rule('.report-status:empty')).not.toContain('display: none')
  })

  it('has hover states for both buttons', () => {
    expect(rule('.report-yes:hover')).not.toBe('')
    expect(rule('.report-no:hover')).not.toBe('')
  })

  it('takes every color from the color variables, so both color modes work', () => {
    const all = ['.report-button', '.report-yes', '.report-no', '.report-yes:hover', '.report-no:hover']
      .map(rule)
      .join('\n')
    expect(all).not.toMatch(/#[0-9a-f]{3,6}\b/i)
  })
})

describe('phone width', () => {
  it('does not hide sideways overflow, so a too wide element shows up in checks', () => {
    expect(css).not.toContain('overflow-x: hidden')
  })
})

describe('the page head', () => {
  it('uses the hiker logo as the site icon', () => {
    expect(indexHtml).toContain('<link rel="icon" type="image/svg+xml" href="/favicon.svg" />')
  })

  it('tints the phone browser bar in both color modes', () => {
    expect(indexHtml).toContain('name="theme-color" media="(prefers-color-scheme: light)"')
    expect(indexHtml).toContain('name="theme-color" media="(prefers-color-scheme: dark)"')
  })
})
