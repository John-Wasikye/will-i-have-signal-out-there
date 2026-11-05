import { useState } from 'react'
import { formatUtc } from '../lib/status'
import {
  distanceKm,
  isReachableAt,
  isRunLate,
  windowsWithPassedFlag,
  type PointSignal,
  type TrailSignal,
} from '../lib/trailSignal'

const BAR_HEIGHT = 24

interface StripRowProps {
  label: string
  barClass: string
  points: PointSignal[]
  isOn: (point: PointSignal) => boolean
}

/** One row of the strip map: a bar at each point where ``isOn`` holds, nothing where it does not. */
function StripRow({ label, barClass, points, isOn }: StripRowProps) {
  const on = points.filter(isOn)
  return (
    <figure className="strip-map">
      <figcaption>{label}</figcaption>
      <svg
        viewBox={`0 0 ${points.length} ${BAR_HEIGHT}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`${label} at ${on.length} of ${points.length} points`}
      >
        <rect className="strip-track" width={points.length} height={BAR_HEIGHT} />
        {on.map((point) => (
          <rect
            key={point.trail_point_id}
            className={barClass}
            x={points.indexOf(point)}
            width={1}
            height={BAR_HEIGHT}
          />
        ))}
      </svg>
    </figure>
  )
}

function PointDetail({ point, now }: { point: PointSignal; now: Date }) {
  const windows = windowsWithPassedFlag(point.windows, now)
  return (
    <section aria-labelledby="point-heading">
      <h3 id="point-heading">About {distanceKm(point.seq).toFixed(2)} km along the trail</h3>
      <ul className="point-coverage">
        {point.coverage.map((item) => (
          <li key={item.carrier}>
            {item.carrier}: {item.covered ? 'covered' : 'not covered'}
          </li>
        ))}
      </ul>
      {windows.length === 0 ? (
        <p>No satellite is predicted to be reachable from this point.</p>
      ) : (
        <ol className="window-list">
          {windows.map((window) => (
            <li
              key={window.start_utc}
              className={window.passed ? 'window window-passed' : 'window'}
            >
              {formatUtc(window.start_utc)} to {formatUtc(window.end_utc)}
              {window.passed && ' (passed)'}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

interface TrailSignalViewProps {
  signal: TrailSignal
  now: Date
}

export function TrailSignalView({ signal, now }: TrailSignalViewProps) {
  const [selected, setSelected] = useState(0)
  const late = isRunLate(signal.valid_until_utc, now)
  const validUntil = formatUtc(signal.valid_until_utc)
  const point = signal.points[Math.min(selected, signal.points.length - 1)]

  return (
    <div className="panel">
      {late ? (
        <div className="notice notice-late" role="status">
          <p>
            Data is late. Last good run: {formatUtc(signal.last_good_run_utc)}. Predictions valid
            until: {validUntil}.
          </p>
        </div>
      ) : (
        <p className="valid-until">Predictions valid until {validUntil}</p>
      )}

      {signal.carriers.map((carrier) => (
        <StripRow
          key={carrier}
          label={`${carrier} coverage`}
          barClass="strip-bar"
          points={signal.points}
          isOn={(item) => item.coverage.some((flag) => flag.carrier === carrier && flag.covered)}
        />
      ))}
      {!late && (
        <StripRow
          label="Satellite reachable now"
          barClass="strip-reach"
          points={signal.points}
          isOn={(item) => isReachableAt(item.windows, now)}
        />
      )}

      <p className="note-text">
        Coverage shown is the FCC's modelled claim, not a measurement. Satellite texts are not
        guaranteed: they need T-Mobile service and a supported phone, and they can fail under cover
        that the terrain model does not show.
      </p>

      <label htmlFor="trail-point">Move along the trail</label>
      <input
        id="trail-point"
        type="range"
        min={0}
        max={signal.points.length - 1}
        value={Math.min(selected, signal.points.length - 1)}
        onChange={(event) => setSelected(Number(event.target.value))}
      />
      <PointDetail point={point} now={now} />
    </div>
  )
}
