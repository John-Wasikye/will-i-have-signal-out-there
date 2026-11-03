import type { ReactElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

/** Renders a React element to HTML. Needs no DOM and no extra test library. */
export function renderMarkup(element: ReactElement): string {
  return renderToStaticMarkup(element)
}

/** The text a reader sees: tags removed, the few entities React writes decoded, spaces tidied. */
export function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, ' ')
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim()
}
