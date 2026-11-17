import { Link } from 'react-router-dom'
import { usePageTitle } from '../lib/usePageTitle'

export function NotFound() {
  usePageTitle('Page not found')
  return (
    <>
      <h1>Page not found</h1>
      <p className="lede">
        I could not find that page. Go back to the <Link to="/">trails</Link>.
      </p>
    </>
  )
}
