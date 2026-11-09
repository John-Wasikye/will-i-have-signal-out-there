/**
 * Hiker signal reports on the phone (C21, part 1).
 *
 * A tap reads the position, turns it into an H3 resolution 9 cell, and keeps only the cell
 * (ADR 0009). The report waits in a queue on the phone and is sent when the page can reach the
 * report API, so a hiker with no signal can still report (ADR 0010). The visitor ID is created
 * once, kept on the phone, and sent only in a header (ADR 0025).
 */
/** The carriers a hiker can pick. platform/serving/reports.py accepts the same list. */
export const CARRIERS = ['AT&T', 'T-Mobile', 'Verizon'] as const
export type Carrier = (typeof CARRIERS)[number]

export interface ReportIn {
  cell: string
  carrier: string
  had_signal: boolean
  report_hour_utc: string
}

/** A report waiting on the phone. The id only tells queued reports apart; it is never sent. */
export interface QueuedReport {
  id: string
  report: ReportIn
}

/** The part of localStorage the queue needs, so tests can use a plain object. */
export interface KeyValueStore {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

export type SendResult =
  | { kind: 'accepted' }
  | { kind: 'refused'; message: string }
  | { kind: 'retry' }

export interface FlushSummary {
  accepted: number
  refused: string[]
  waiting: number
}

const KEYS = {
  visitorId: 'signal.visitorId',
  queue: 'signal.reportQueue',
  carrier: 'signal.carrier',
}
const HOUR_MS = 3_600_000
// The report API refuses a report hour more than 48 hours before it arrives (ADR 0026).
const MAX_REPORT_AGE_MS = 48 * HOUR_MS
const TOO_OLD = 'A saved report was more than 48 hours old, so it was not sent.'
const REFUSED = 'The report was not accepted.'

/** Return the phone's visitor ID, creating it the first time: 16 random bytes as hexadecimal. */
export function getOrCreateVisitorId(
  store: KeyValueStore,
  randomBytes: (length: number) => Uint8Array,
): string {
  const stored = store.getItem(KEYS.visitorId)
  if (stored !== null && /^[0-9a-f]{32}$/.test(stored)) return stored
  const id = Array.from(randomBytes(16), (byte) => byte.toString(16).padStart(2, '0')).join('')
  store.setItem(KEYS.visitorId, id)
  return id
}

/** The report's time: the start of its hour, in UTC, like 2026-11-09T18:00:00Z. */
export function reportHourUtc(now: Date): string {
  const hour = new Date(Math.floor(now.getTime() / HOUR_MS) * HOUR_MS)
  return hour.toISOString().replace('.000Z', 'Z')
}

export function buildReport(cell: string, carrier: Carrier, hadSignal: boolean, now: Date): ReportIn {
  return { cell, carrier, had_signal: hadSignal, report_hour_utc: reportHourUtc(now) }
}

function isQueuedReport(value: unknown): value is QueuedReport {
  if (typeof value !== 'object' || value === null) return false
  const item = value as Partial<QueuedReport>
  return typeof item.id === 'string' && typeof item.report?.report_hour_utc === 'string'
}

/** The reports waiting on the phone, oldest first. Damaged storage reads as no reports. */
export function loadQueue(store: KeyValueStore): QueuedReport[] {
  try {
    const parsed: unknown = JSON.parse(store.getItem(KEYS.queue) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter(isQueuedReport) : []
  } catch {
    return []
  }
}

function saveQueue(store: KeyValueStore, queue: QueuedReport[]): void {
  store.setItem(KEYS.queue, JSON.stringify(queue))
}

/** Add a report to the queue and return how many now wait. */
export function enqueueReport(store: KeyValueStore, report: ReportIn, id: string): number {
  const queue = [...loadQueue(store), { id, report }]
  saveQueue(store, queue)
  return queue.length
}

function removeFromQueue(store: KeyValueStore, id: string): void {
  saveQueue(
    store,
    loadQueue(store).filter((item) => item.id !== id),
  )
}

async function serverMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: { message?: unknown } }
    return typeof body.error?.message === 'string' ? body.error.message : REFUSED
  } catch {
    return REFUSED
  }
}

/** Post one report. Network trouble and server outages mean try again later. */
export async function sendReport(
  url: string,
  visitorId: string,
  report: ReportIn,
  fetchImpl: typeof fetch,
): Promise<SendResult> {
  let response: Response
  try {
    response = await fetchImpl(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-visitor-id': visitorId },
      body: JSON.stringify({
        cell: report.cell,
        carrier: report.carrier,
        had_signal: report.had_signal,
        report_hour_utc: report.report_hour_utc,
      }),
    })
  } catch {
    return { kind: 'retry' }
  }
  if (response.status === 202) return { kind: 'accepted' }
  if (response.status === 400 || response.status === 429) {
    return { kind: 'refused', message: await serverMessage(response) }
  }
  return { kind: 'retry' }
}

/**
 * Send the waiting reports in order. A refused report is dropped, because sending it again
 * cannot succeed. The first one that cannot be sent stops the run, and it and the rest wait for
 * the next try. Each report is removed by its id, so one added meanwhile is kept.
 */
export async function flushQueue(
  store: KeyValueStore,
  send: (report: ReportIn) => Promise<SendResult>,
  now: Date,
): Promise<FlushSummary> {
  const summary: FlushSummary = { accepted: 0, refused: [], waiting: 0 }
  for (const item of loadQueue(store)) {
    if (now.getTime() - Date.parse(item.report.report_hour_utc) > MAX_REPORT_AGE_MS) {
      removeFromQueue(store, item.id)
      summary.refused.push(TOO_OLD)
      continue
    }
    const result = await send(item.report)
    if (result.kind === 'retry') break
    removeFromQueue(store, item.id)
    if (result.kind === 'accepted') summary.accepted += 1
    else summary.refused.push(result.message)
  }
  summary.waiting = loadQueue(store).length
  return summary
}

export function loadCarrier(store: KeyValueStore): Carrier | null {
  const stored = store.getItem(KEYS.carrier)
  return CARRIERS.find((carrier) => carrier === stored) ?? null
}

export function saveCarrier(store: KeyValueStore, carrier: Carrier): void {
  store.setItem(KEYS.carrier, carrier)
}

/** "1 report waiting to send", "3 reports waiting to send", or nothing. */
export function waitingNote(count: number): string {
  if (count === 0) return ''
  return `${count} ${count === 1 ? 'report' : 'reports'} waiting to send`
}
