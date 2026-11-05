import { useEffect, useMemo, useState, type MouseEvent } from 'react'
import { formatUtc } from '../lib/status'
import {
  distanceKm,
  isReachableAt,
  isRunLate,
  nearestPoint,
  nextWalkStep,
  nextWindow,
  pointState,
  trailRuns,
  trailShape,
  windowsWithPassedFlag,
  type MapPoint,
  type PointSignal,
  type PointState,
  type TrailSignal,
} from '../lib/trailSignal'

const MAP_WIDTH = 600
const MAP_HEIGHT = 420
const MAP_PADDING = 34
const WALK_TICK_MS = 50
const FULL_SIGNAL_BARS = [1, 2, 3, 4]

function linePoints(shape: MapPoint[]): string {
  return shape.map(({ x, y }) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
}

/** A run of one point still needs a line, so it reaches back to the point before it. */
function runShape(shape: MapPoint[], start: number, end: number): MapPoint[] {
  return shape.slice(end === shape.length - 1 ? Math.max(start - 1, 0) : start, end + 2)
}

interface TrailMapProps {
  shape: MapPoint[]
  states: PointState[]
  selected: number
  label: string
  onSelect: (index: number) => void
}

function TrailMap({ shape, states, selected, label, onSelect }: TrailMapProps) {
  const you = shape[selected]
  const start = shape[0]
  const end = shape[shape.length - 1]

  function selectNearest(event: MouseEvent<SVGSVGElement>) {
    const box = event.currentTarget.getBoundingClientRect()
    const x = ((event.clientX - box.left) / box.width) * MAP_WIDTH
    const y = ((event.clientY - box.top) / box.height) * MAP_HEIGHT
    onSelect(nearestPoint(shape, x, y))
  }

  return (
    <figure className="strip-map">
      <svg viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`} role="img" aria-label={label} onClick={selectNearest}>
        <polyline className="trail-casing" points={linePoints(shape)} />
        {trailRuns(states).map((run) => (
          <polyline
            key={run.start}
            className={`trail-run trail-run-${run.state}`}
            points={linePoints(runShape(shape, run.start, run.end))}
          />
        ))}
        <circle className="trail-end" cx={start.x} cy={start.y} r={6} />
        <text className="trail-label" x={start.x} y={start.y + 30}>
          Start
        </text>
        <circle className="trail-end" cx={end.x} cy={end.y} r={6} />
        <text className="trail-label" x={end.x} y={end.y - 12}>
          End
        </text>
        <circle className="trail-you-halo" cx={you.x} cy={you.y} r={17} />
        <circle className="trail-you" cx={you.x} cy={you.y} r={9} />
      </svg>
    </figure>
  )
}

function MapKey({ carrier, late }: { carrier: string; late: boolean }) {
  return (
    <ul className="map-key" aria-label="Map key">
      <li>
        <span className="key-line key-covered" />
        {carrier} claims coverage
      </li>
      {!late && (
        <li>
          <span className="key-line key-satellite" />
          No {carrier}, but a satellite is reachable now
        </li>
      )}
      <li>
        <span className="key-line key-none" />
        {late ? 'No coverage claimed' : 'Neither right now'}
      </li>
      <li>
        <span className="key-you" />
        You are here
      </li>
    </ul>
  )
}

function SignalBars({ on }: { on: boolean }) {
  return (
    <svg className={on ? 'signal-bars signal-bars-on' : 'signal-bars'} viewBox="0 0 28 24" aria-hidden="true">
      {FULL_SIGNAL_BARS.map((bar) => (
        <rect key={bar} x={(bar - 1) * 7} y={24 - bar * 6} width={5} height={bar * 6} rx={1} />
      ))}
    </svg>
  )
}

function satelliteAnswer(point: PointSignal, now: Date, late: boolean): string {
  if (late) return 'Data is late, see the windows below'
  if (isReachableAt(point.windows, now)) return 'Reachable now'
  const next = nextWindow(point.windows, now)
  return next ? `Next: ${formatUtc(next.start_utc)}` : 'No window predicted'
}

function PointDetail({ point, now, late }: { point: PointSignal; now: Date; late: boolean }) {
  const windows = windowsWithPassedFlag(point.windows, now)
  const covered = point.coverage.some((item) => item.covered)
  return (
    <section className="point-detail" aria-labelledby="point-heading">
      <h3 id="point-heading">About {distanceKm(point.seq).toFixed(2)} km along the trail</h3>
      <div className="answer-tiles">
        <div className={covered ? 'answer-tile answer-yes' : 'answer-tile'}>
          <p className="answer-label">Phone</p>
          <SignalBars on={covered} />
          <ul className="point-coverage">
            {point.coverage.map((item) => (
              <li key={item.carrier}>
                {item.carrier}: {item.covered ? 'covered' : 'not covered'}
              </li>
            ))}
          </ul>
        </div>
        <div className="answer-tile">
          <p className="answer-label">Satellite</p>
          <p className="answer-value">{satelliteAnswer(point, now, late)}</p>
        </div>
      </div>
      <h4>Satellite windows from this spot</h4>
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
  const [walking, setWalking] = useState(false)
  const lastIndex = signal.points.length - 1
  const late = isRunLate(signal.valid_until_utc, now)
  const validUntil = formatUtc(signal.valid_until_utc)
  const point = signal.points[Math.min(selected, lastIndex)]
  const shape = useMemo(
    () => trailShape(signal.points, MAP_WIDTH, MAP_HEIGHT, MAP_PADDING),
    [signal.points],
  )
  // Checking every window of every point is too slow to repeat on each step of a walk.
  const states = useMemo(
    () => signal.points.map((item) => pointState(item, now, late)),
    [signal.points, now, late],
  )
  const reachCount = useMemo(
    () => signal.points.filter((item) => isReachableAt(item.windows, now)).length,
    [signal.points, now],
  )
  const carrier = signal.carriers[0]
  const coveredCount = signal.points.filter((item) =>
    item.coverage.some((flag) => flag.covered),
  ).length
  const coverageLabel = `${carrier} coverage at ${coveredCount} of ${signal.points.length} points.`
  const reachLabel = `Satellite reachable now at ${reachCount} of ${signal.points.length} points.`

  useEffect(() => {
    if (!walking) return
    const timer = setInterval(() => {
      setSelected((index) => {
        const next = nextWalkStep(index, lastIndex)
        if (next === lastIndex) setWalking(false)
        return next
      })
    }, WALK_TICK_MS)
    return () => clearInterval(timer)
  }, [walking, lastIndex])

  function toggleWalk() {
    if (!walking && selected >= lastIndex) setSelected(0)
    setWalking(!walking)
  }

  function jumpTo(index: number) {
    setWalking(false)
    setSelected(index)
  }

  return (
    <>
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

      <div className="walker">
        <div className="panel walker-map">
          <div className="walk-controls">
            <button type="button" className="walk-button" onClick={toggleWalk}>
              {walking ? 'Pause' : 'Walk the trail'}
            </button>
            <div className="walk-slider">
              <label htmlFor="trail-point">Move along the trail</label>
              <input
                id="trail-point"
                type="range"
                min={0}
                max={lastIndex}
                value={Math.min(selected, lastIndex)}
                onChange={(event) => jumpTo(Number(event.target.value))}
              />
            </div>
          </div>
          <TrailMap
            shape={shape}
            states={states}
            selected={Math.min(selected, lastIndex)}
            label={late ? coverageLabel : `${coverageLabel} ${reachLabel}`}
            onSelect={jumpTo}
          />
          <MapKey carrier={carrier} late={late} />
        </div>
        <div className="panel walker-detail">
          <PointDetail point={point} now={now} late={late} />
        </div>
      </div>

      <p className="note-text">
        Coverage shown is the FCC's modelled claim, not a measurement. Satellite texts are not
        guaranteed: they need T-Mobile service and a supported phone, and they can fail under cover
        that the terrain model does not show.
      </p>
    </>
  )
}
