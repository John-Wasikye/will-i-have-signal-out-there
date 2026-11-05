import { Logo } from './Logo'
import { MountainBackdrop } from './MountainBackdrop'

/** The opening of the trail tool: a small hiker under big peaks, with the site's question. */
export function Hero() {
  return (
    <div className="hero">
      <div className="hero-text">
        <h1>Will I have signal out there?</h1>
        <p>Walk a Grand Canyon trail here first, and see where your phone could work.</p>
      </div>
      <div className="hero-scene">
        <MountainBackdrop />
        <div className="hero-hiker">
          <Logo />
        </div>
      </div>
    </div>
  )
}
