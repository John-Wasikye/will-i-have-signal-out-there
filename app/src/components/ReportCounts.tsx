import { carrierTotals, type ReportCount } from '../lib/reportCounts'

interface ReportCountsProps {
  /** The trail's counts, or null while they load or after they failed. */
  counts: ReportCount[] | null
  failed: boolean
}

/** What hikers reported along the chosen trail in the last 7 days (C23, ADR 0030). */
export function ReportCounts({ counts, failed }: ReportCountsProps) {
  if (failed) {
    return (
      <section className="report-counts" aria-label="Hiker reports">
        <p className="error-text">Hiker reports could not be loaded.</p>
      </section>
    )
  }
  if (counts === null) return null

  const totals = carrierTotals(counts)
  return (
    <section className="report-counts" aria-label="Hiker reports">
      <h3>Hiker reports along this trail, last 7 days</h3>
      {totals.length === 0 ? (
        <p>Too few reports to show.</p>
      ) : (
        <ul>
          {totals.map((total) => (
            <li key={total.carrier}>
              {total.carrier}: {total.withSignal} had signal, {total.withoutSignal} had no signal
            </li>
          ))}
        </ul>
      )}
      <p className="report-counts-note">
        These are hikers' own reports, not checked. An area is shown only once it has at least 5
        reports.
      </p>
    </section>
  )
}
