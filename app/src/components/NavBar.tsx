import { NavLink } from 'react-router-dom'

export function NavBar() {
  return (
    <header className="site-header">
      <nav aria-label="Main">
        <ul className="nav-list">
          <li>
            <NavLink to="/">Home</NavLink>
          </li>
          <li>
            <NavLink to="/lookup">Lookup</NavLink>
          </li>
          <li>
            <NavLink to="/status">Status</NavLink>
          </li>
        </ul>
      </nav>
    </header>
  )
}
