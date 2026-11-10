/** One area's count for one carrier and answer (docs/trip-planner/openapi.yaml, ReportCount). */
export interface ReportCount {
  area_id: string
  carrier: string
  had_signal: boolean
  report_count: number
}

export interface CarrierTotal {
  carrier: string
  withSignal: number
  withoutSignal: number
}

/**
 * Add up each carrier's reports over the areas along a trail. The API sends only areas with at
 * least 5 reports in 7 days (ADR 0030), so every number here already passed that minimum.
 */
export function carrierTotals(counts: ReportCount[]): CarrierTotal[] {
  const totals = new Map<string, CarrierTotal>()
  for (const count of counts) {
    const total = totals.get(count.carrier) ?? {
      carrier: count.carrier,
      withSignal: 0,
      withoutSignal: 0,
    }
    if (count.had_signal) total.withSignal += count.report_count
    else total.withoutSignal += count.report_count
    totals.set(count.carrier, total)
  }
  return [...totals.values()].sort((a, b) => a.carrier.localeCompare(b.carrier))
}
