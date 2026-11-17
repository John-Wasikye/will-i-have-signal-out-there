import { useEffect } from 'react'

const SITE_NAME = 'Will I have signal out there?'

export function pageTitle(name: string): string {
  return `${name} | ${SITE_NAME}`
}

/** Sets the browser tab title, so a history list and a screen reader tell the pages apart. */
export function usePageTitle(name: string): void {
  useEffect(() => {
    document.title = pageTitle(name)
  }, [name])
}
