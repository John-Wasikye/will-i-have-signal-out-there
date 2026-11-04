import { Link } from 'react-router-dom'
import { Credits } from '../components/Credits'
import { DtcRequirementsNote } from '../components/DtcRequirementsNote'
import { MapView } from '../components/MapView'

export function Home() {
  return (
    <>
      <h1>Will I have signal out there?</h1>
      <p>
        I am building a trip planner for hikers at Grand Canyon National Park. It will show where
        T-Mobile has coverage along a trail, and when a satellite text could get through. The planner
        is not finished, so it does not show any coverage or satellite times yet. You can see the{' '}
        <Link to="/trails">trail names</Link> or check the <Link to="/status">status page</Link>.
      </p>

      <section aria-labelledby="will-do-heading">
        <h2 id="will-do-heading">What the planner will do</h2>
        <ul>
          <li>
            A strip map shows coverage bars along a trail. Bars mark where T-Mobile has coverage, and
            no bars mark where it does not.
          </li>
          <li>
            Satellite text windows show when a Direct-to-Cell text, sent through a Starlink satellite
            to a supported phone, could get through. The planner accounts for canyon walls that block
            the sky.
          </li>
          <li>
            Each set of predictions shows a "Predictions valid until" time, in your local time, so you
            can see how old the predictions are.
          </li>
        </ul>
      </section>

      <section aria-labelledby="scope-heading">
        <h2 id="scope-heading">Phase A scope</h2>
        <ul>
          <li>The main trails at Grand Canyon National Park: Bright Angel, South Kaibab and North Kaibab.</li>
          <li>One carrier: T-Mobile.</li>
          <li>The next 24 hours.</li>
        </ul>
      </section>

      <section aria-labelledby="how-heading">
        <h2 id="how-heading">How it works</h2>
        <p>
          Once the data pipeline is finished, an automated job will run every night at 10:00 UTC
          (Coordinated Universal Time). It will collect the latest data, check it, and publish the
          results as data files.
        </p>
        <p>
          The page asks a small web service for the answers, and that service reads the published
          files. The machine that runs the nightly job is switched off the rest of the day, and the
          page keeps working without it.
        </p>
      </section>

      <section aria-labelledby="map-heading">
        <h2 id="map-heading">Map preview</h2>
        <MapView />
      </section>

      <DtcRequirementsNote />
      <Credits />
    </>
  )
}
