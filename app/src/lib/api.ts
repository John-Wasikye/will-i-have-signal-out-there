/**
 * The address of one sample lookup. The API serves /sample at the root of its address
 * (docs/platform/openapi-serving-template.yaml). The key is encoded, so it cannot change the
 * address.
 */
export function sampleUrl(baseUrl: string, key: string): string {
  return `${baseUrl.replace(/\/$/, '')}/sample?key=${encodeURIComponent(key)}`
}

/** The address of the trail list (docs/trip-planner/openapi.yaml). */
export function trailsUrl(baseUrl: string): string {
  return `${baseUrl.replace(/\/$/, '')}/trails`
}

/** The address of one trail's signal. The ID is encoded, so it cannot change the address. */
export function trailSignalUrl(baseUrl: string, trailId: string): string {
  return `${trailsUrl(baseUrl)}/${encodeURIComponent(trailId)}/signal`
}

/** The address hiker reports are posted to (docs/trip-planner/openapi.yaml, Phase B). */
export function reportsUrl(baseUrl: string): string {
  return `${baseUrl.replace(/\/$/, '')}/reports`
}

/**
 * The address of the hiker report counts for one trail (docs/trip-planner/openapi.yaml, Phase B).
 * The trail ID is encoded, so it cannot change the address.
 */
export function reportCountsUrl(baseUrl: string, trailId: string): string {
  return `${baseUrl.replace(/\/$/, '')}/report-counts?trail_id=${encodeURIComponent(trailId)}`
}
