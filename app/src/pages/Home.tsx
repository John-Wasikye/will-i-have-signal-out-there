import { Link } from 'react-router-dom'
import { MapView } from '../components/MapView'

export function Home() {
  return (
    <>
      <h1>Will I have signal out there?</h1>
      <p>
        I am building a trip planner for hikers and campers. It will show where each phone carrier
        has coverage, and when a satellite text could get through. You can check whether the
        nightly data run is up to date on the <Link to="/status">status page</Link>, or try the{' '}
        <Link to="/lookup">lookup page</Link>.
      </p>

      <section aria-labelledby="map-heading">
        <h2 id="map-heading">Map preview</h2>
        <MapView />
      </section>
    </>
  )
}
