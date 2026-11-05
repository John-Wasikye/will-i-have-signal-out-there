import { formatUtc } from '../lib/status'
import { freshness } from '../lib/trailSignal'

interface DataFreshnessProps {
  lastGoodRunUtc: string
  validUntilUtc: string
  now: Date
}

function timeLeft(hours: number): string {
  if (hours < 1) return 'less than an hour'
  const rounded = Math.round(hours)
  return `about ${rounded} more ${rounded === 1 ? 'hour' : 'hours'}`
}

/** The answer a hiker wants from the status page: can I trust what the trail map shows? */
export function DataFreshness({ lastGoodRunUtc, validUntilUtc, now }: DataFreshnessProps) {
  const { hoursLeft, shareLeft, late } = freshness(lastGoodRunUtc, validUntilUtc, now)
  const validUntil = formatUtc(validUntilUtc)

  return (
    <section className={late ? 'freshness freshness-late' : 'freshness'} aria-label="Trail data">
      {late ? (
        <div className="notice notice-late" role="status">
          <p>
            Data is late. Last good run: {formatUtc(lastGoodRunUtc)}. Predictions valid until:{' '}
            {validUntil}.
          </p>
        </div>
      ) : (
        <>
          <p className="freshness-state">Up to date</p>
          <p>The trail predictions are good for {timeLeft(hoursLeft)}.</p>
          <meter
            className="freshness-meter"
            min={0}
            max={1}
            value={shareLeft}
            aria-label="Share of the prediction time left"
          />
        </>
      )}
      <dl className="facts">
        <dt>Last good run</dt>
        <dd>{formatUtc(lastGoodRunUtc)}</dd>
        <dt>Valid until</dt>
        <dd>{validUntil}</dd>
        <dt>Next update</dt>
        <dd>A new run starts every night at 10:00 UTC (Coordinated Universal Time).</dd>
      </dl>
    </section>
  )
}
