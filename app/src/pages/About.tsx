import { Link } from 'react-router-dom'
import { Credits } from '../components/Credits'
import { DtcRequirementsNote } from '../components/DtcRequirementsNote'
import { usePageTitle } from '../lib/usePageTitle'

export function About() {
  usePageTitle('How it works')
  return (
    <>
      <h1>How it works</h1>
      <p className="lede">
        I am building a trip planner for hikers at Grand Canyon National Park. It shows where AT&T,
        T-Mobile and Verizon claim coverage along a trail, and when a satellite text could get
        through. Try a <Link to="/">trail</Link> or check the <Link to="/status">status page</Link>.
      </p>

      <section className="panel" aria-labelledby="will-do-heading">
        <h2 id="will-do-heading">What the planner does</h2>
        <ul>
          <li>
            A trail map colors each stretch of a trail, so you can see where a carrier claims
            coverage and where it does not. A carrier picker above the map switches between AT&T,
            T-Mobile and Verizon.
          </li>
          <li>
            Satellite text windows show when a Direct-to-Cell text, sent through a Starlink satellite
            to a supported phone, could get through. Satellite texting needs T-Mobile, so the map
            shows satellite reach only when T-Mobile is the chosen carrier. The planner accounts for
            canyon walls that block the sky.
          </li>
          <li>
            Each set of predictions shows a "Predictions valid until" time, in your local time, so you
            can see how old the predictions are.
          </li>
          <li>
            Hiker reports let you tell other hikers where you had signal and where you did not. A
            report is one tap on "I had signal here" or "I had no signal here". Only an area about
            350 m across, your carrier and the hour leave your phone. The page shows counts for an
            area once it has at least 5 reports in 7 days.
          </li>
        </ul>
      </section>

      <section className="panel" aria-labelledby="scope-heading">
        <h2 id="scope-heading">What it covers today</h2>
        <ul>
          <li>Three trails at Grand Canyon National Park: Bright Angel, South Kaibab and North Kaibab.</li>
          <li>
            Three carriers, AT&T, T-Mobile and Verizon, on 4G LTE (Long-Term Evolution) and 5G, from
            the map of the Federal Communications Commission (FCC).
          </li>
          <li>Satellite texts on T-Mobile.</li>
          <li>The next 24 hours, refreshed every night.</li>
          <li>Reports from hikers.</li>
        </ul>
      </section>

      <section className="panel" aria-labelledby="later-heading">
        <h2 id="later-heading">Still to come</h2>
        <p>
          I want to cover more places than Grand Canyon. I also want to add a confidence rating for
          each stretch of a trail, built from hiker reports and speed tests.
        </p>
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
