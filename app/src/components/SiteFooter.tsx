import { Link } from 'react-router-dom'

const SOURCE_URL = 'https://github.com/John-Wasikye/will-i-have-signal-out-there'

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <p>
        I built this site as a portfolio project. I have not checked its predictions in the field,
        so do not rely on it for your safety.
      </p>
      <ul className="footer-links">
        <li>
          <Link to="/about">How it works</Link>
        </li>
        <li>
          <Link to="/status">Status</Link>
        </li>
        <li>
          <Link to="/about#credits-heading">Data sources and credits</Link>
        </li>
        <li>
          <a href={SOURCE_URL} rel="noopener noreferrer">
            Source code on GitHub
          </a>
        </li>
      </ul>
    </footer>
  )
}
