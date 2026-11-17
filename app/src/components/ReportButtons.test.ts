import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { renderMarkup, visibleText } from '../testing/markup'
import { ReportButtons } from './ReportButtons'

describe('ReportButtons', () => {
  const markup = renderMarkup(createElement(ReportButtons))
  const text = visibleText(markup)

  // The buttons carry a hidden check mark or cross, so the plain words are what is left once
  // the hidden parts are taken out, which is also the name a screen reader gives.
  const buttons = (markup.match(/<button[^>]*>.*?<\/button>/g) ?? []).map((button) => ({
    html: button,
    name: visibleText(button.replace(/<span[^>]*aria-hidden="true"[^>]*>.*?<\/span>/g, '')),
  }))

  it('starts with a heading that tells a hiker on the trail what to do', () => {
    expect(markup).toContain('<h2 id="report-heading">On the trail right now? Report your signal</h2>')
    expect(text).not.toContain('Tell other hikers')
  })

  it('asks one question', () => {
    expect(text).toContain('Do you have signal where you are standing?')
  })

  it('offers both report buttons, named in the present tense (FR-49)', () => {
    expect(buttons.map((button) => button.name)).toEqual(['Yes, I have signal', 'No signal'])
  })

  it('has dropped the old button words', () => {
    expect(text).not.toContain('I had signal here')
    expect(text).not.toContain('I had no signal here')
  })

  it('styles the buttons as answers, not as the trail picker', () => {
    expect(buttons[0].html).toMatch(/class="report-button report-yes"/)
    expect(buttons[1].html).toMatch(/class="report-button report-no"/)
    expect(markup).not.toContain('trail-choice')
  })

  it('hides the check mark and the cross from screen readers', () => {
    expect(buttons[0].html).toContain('<span class="report-mark" aria-hidden="true">')
    expect(buttons[1].html).toContain('<span class="report-mark" aria-hidden="true">')
  })

  it('puts the carrier picker before the buttons', () => {
    expect(markup.indexOf('Your carrier')).toBeLessThan(markup.indexOf('report-yes'))
  })

  it('shows the answer to a tap directly after the buttons, before the privacy note', () => {
    const buttonsAt = markup.lastIndexOf('</button>')
    const statusAt = markup.indexOf('class="report-status"')
    const privacyAt = markup.indexOf('Your phone will ask for your location.')
    expect(buttonsAt).toBeLessThan(statusAt)
    expect(statusAt).toBeLessThan(privacyAt)
  })

  it('keeps the status line in the page with nothing inside it until there is a message', () => {
    expect(markup).toMatch(/<p aria-live="polite" class="report-status"><\/p>/)
  })

  it('has a privacy note under the status line, with the area in feet too', () => {
    expect(text).toContain(
      'Your phone will ask for your location. Only an area about 350 m (1,150 ft) across, your ' +
        'carrier and the hour are sent. Your exact position never leaves your phone.',
    )
  })

  it('folds the explanation for no signal away in a details element, after the privacy note', () => {
    const details = markup.slice(markup.indexOf('<details'))
    expect(markup.indexOf('<details')).toBeGreaterThan(markup.indexOf('Your exact position'))
    expect(details).toMatch(/<summary[^>]*>How it works without signal<\/summary>/)
    expect(visibleText(details)).toContain(
      'A report waits on your phone. Android sends it by itself when signal returns, even with ' +
        'this page closed. On iPhone, open this page again when you have signal.',
    )
  })

  it('lets the hiker pick each carrier the API accepts', () => {
    for (const carrier of ['AT&amp;T', 'T-Mobile', 'Verizon']) {
      expect(markup).toContain(`<option value="${carrier}">`)
    }
    expect(markup).toContain('<label')
  })

  it('says the exact position stays on the phone (ADR 0009)', () => {
    expect(text).toContain('Your exact position never leaves your phone')
  })

  it('says a report waits on the phone when there is no signal (ADR 0010)', () => {
    expect(text).toContain('waits on your phone')
  })

  it('says Android sends it by itself and iPhone needs the page open (FR-52)', () => {
    expect(text).toContain('Android sends it by itself when signal returns')
    expect(text).toContain('On iPhone, open this page again')
  })

  it('has a live region for what happened to a report', () => {
    expect(markup).toContain('aria-live="polite"')
  })
})
