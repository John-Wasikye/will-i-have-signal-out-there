import { Link } from 'react-router-dom'
import { MapView } from '../components/MapView'

export function Home() {
  return (
    <>
      <h1>Data platform</h1>
      <p>
        This site runs the data platform behind my projects. You can check whether the nightly
        data run is up to date on the <Link to="/status">status page</Link>, or try the{' '}
        <Link to="/lookup">lookup page</Link>.
      </p>

      <section aria-labelledby="map-heading">
        <h2 id="map-heading">Map preview</h2>
        <MapView />
      </section>
    </>
  )
}
