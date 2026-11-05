import { Link, NavLink } from 'react-router-dom'
import { Logo } from './Logo'
import { MountainBackdrop } from './MountainBackdrop'

export function NavBar() {
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
              <NavLink to="/">Home</NavLink>
            </li>
            <li>
              <NavLink to="/trails">Trails</NavLink>
            </li>
            <li>
              <NavLink to="/lookup">Lookup</NavLink>
            </li>
            <li>
              <NavLink to="/status">Status</NavLink>
            </li>
          </ul>
        </nav>
      </div>
      <MountainBackdrop />
    </header>
  )
}
