import { Link } from 'react-router-dom'
import { Credits } from '../components/Credits'
import { DtcRequirementsNote } from '../components/DtcRequirementsNote'

export function About() {
  return (
    <>
      <h1>How it works</h1>
      <p className="lede">
        I am building a trip planner for hikers at Grand Canyon National Park. It shows where
        T-Mobile claims coverage along a trail, and when a satellite text could get through. Try a{' '}
        <Link to="/">trail</Link> or check the <Link to="/status">status page</Link>.
      </p>

      <section className="panel" aria-labelledby="will-do-heading">
        <h2 id="will-do-heading">What the planner does</h2>
        <ul>
          <li>
            A trail map colors each stretch of a trail, so you can see where T-Mobile has coverage
            and where it does not.
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

      <section className="panel" aria-labelledby="scope-heading">
        <h2 id="scope-heading">Phase A scope</h2>
        <ul>
          <li>The main trails at Grand Canyon National Park: Bright Angel, South Kaibab and North Kaibab.</li>
          <li>One carrier: T-Mobile.</li>
          <li>The next 24 hours.</li>
        </ul>
      </section>

      <section className="panel" aria-labelledby="how-heading">
        <h2 id="how-heading">Behind the scenes</h2>
        <p>
          An automated job runs every night at 10:00 UTC (Coordinated Universal Time). It collects
          the latest data, checks it, and publishes the results as data files.
        </p>
        <p>
          The page asks a small web service for the answers, and that service reads the published
          files. The machine that runs the nightly job is switched off the rest of the day, and the
          page keeps working without it.
        </p>
      </section>

      <DtcRequirementsNote />
      <Credits />
    </>
  )
}
