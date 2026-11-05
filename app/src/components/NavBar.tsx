import { Link, NavLink, useLocation } from 'react-router-dom'
import { Hero } from './Hero'
import { Logo } from './Logo'
import { MountainBackdrop } from './MountainBackdrop'

const TRAIL_TOOL_PATHS = ['/', '/trails']

export function NavBar() {
  const { pathname } = useLocation()
  return (
    <header className="site-header">
      <div className="header-bar">
        <Link className="brand" to="/">
          <Logo />
          <span>Will I have signal out there?</span>
        </Link>
        <nav aria-label="Main">
          <ul className="nav-list">
            <li>
              <NavLink to="/" end>
                Trails
              </NavLink>
            </li>
            <li>
              <NavLink to="/about">How it works</NavLink>
            </li>
            <li>
              <NavLink to="/status">Status</NavLink>
            </li>
          </ul>
        </nav>
      </div>
      {TRAIL_TOOL_PATHS.includes(pathname) ? <Hero /> : <MountainBackdrop />}
    </header>
  )
}
