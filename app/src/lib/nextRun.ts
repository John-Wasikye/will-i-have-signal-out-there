// The nightly job starts at this hour, UTC. The text on the About and Status pages says the same.
const RUN_HOUR_UTC = 10

/** The next nightly run after a given moment. A run that starts at this very moment is not next. */
export function nextNightlyRun(now: Date): Date {
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), RUN_HOUR_UTC)
  const dayMs = 24 * 60 * 60 * 1000
  return new Date(today > now.getTime() ? today : today + dayMs)
}
