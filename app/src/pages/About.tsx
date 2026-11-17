import { Link } from 'react-router-dom'
import { BuildDiagram } from '../components/BuildDiagram'
import { Credits } from '../components/Credits'
import { DtcRequirementsNote } from '../components/DtcRequirementsNote'
import { REPORT_AREA_WIDTH_M } from '../lib/reports'
import { formatAreaWidth } from '../lib/units'
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
            report is one tap on "Yes, I have signal" or "No signal". Only an area about{' '}
            {formatAreaWidth(REPORT_AREA_WIDTH_M)} across, your carrier and the hour leave your
            phone. The page shows counts for an area once it has at least 5 reports in 7 days.
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

      <section className="panel" aria-labelledby="built-heading">
        <h2 id="built-heading">How it is built</h2>
        <p>
          The planner is a chain of steps. Each step hands its result to the next one, and a check
          sits before anything reaches this page.
        </p>
        <BuildDiagram />
        <ol className="build-steps">
          <li>
            <strong>Public data.</strong> Orbits come from CelesTrak, trails from the National Park
            Service, coverage from the FCC and terrain heights from Copernicus.
          </li>
          <li>
            <strong>Nightly job.</strong> Airflow starts the tasks in the right order, and Spark
            processes the data in parallel. The tasks cut each trail into points, work out how much
            sky the canyon walls block at each point, and find when a satellite could be overhead.
            They run on a server that starts every night and is switched off when they finish.
          </li>
          <li>
            <strong>Data lake.</strong> The results are stored as Iceberg tables, an open table
            format, on S3, Amazon's Simple Storage Service. I keep the raw files too, with a hash
            and the time I fetched them.
          </li>
          <li>
            <strong>Checked marts.</strong> dbt (data build tool) turns the lake tables into tidy
            tables for the page, called marts, and tests them. It runs on DuckDB, a small database
            that runs inside a program. The publish gate then checks the result, and only a result
            that passes is written out as Parquet files, a column-based file format. If a check
            fails, nothing new is published, the page keeps the last good data, and I get an
            alert.
          </li>
          <li>
            <strong>Small web service and this page.</strong> A web service written with FastAPI
            runs on Lambda, Amazon's service that runs code only when it is asked. It reads the
            published files, so it answers even while the nightly server is off. This page is
            written with React and served as static files through CloudFront, Amazon's content
            delivery network.
          </li>
        </ol>
        <p>
          The design document and the decision records are in the public repository:{' '}
          <a
            href="https://github.com/John-Wasikye/will-i-have-signal-out-there/tree/main/docs/trip-planner"
            rel="noopener noreferrer"
          >
            the planner design and decisions
          </a>{' '}
          and{' '}
          <a
            href="https://github.com/John-Wasikye/will-i-have-signal-out-there/tree/main/docs/platform"
            rel="noopener noreferrer"
          >
            the platform design and decisions
          </a>
          .
        </p>
      </section>

      <DtcRequirementsNote />
      <Credits />
    </>
  )
}
