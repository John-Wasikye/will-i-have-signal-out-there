import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

/**
 * The router keeps the scroll position when the page changes, so a footer link would open the next
 * page at the bottom. A link with a hash, like the credits link, scrolls to that heading instead.
 */
export function ScrollOnNavigate() {
  const { pathname, hash } = useLocation()
  useEffect(() => {
    const target = hash ? document.getElementById(hash.slice(1)) : null
    if (target) target.scrollIntoView()
    else window.scrollTo(0, 0)
  }, [pathname, hash])
  return null
}
