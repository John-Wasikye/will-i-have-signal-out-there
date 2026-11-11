/**
 * Hiker signal reports on the phone (C21).
 *
 * A tap reads the position, turns it into an H3 resolution 9 cell, and keeps only the cell
 * (ADR 0009). The report waits in a queue on the phone and is sent when the phone can reach the
 * report API, so a hiker with no signal can still report (ADR 0010). The visitor ID is created
 * once, kept on the phone, and sent only in a header (ADR 0025).
 *
 * Part 2: the queue lives in a store the page and the background sender (a service worker,
 * src/sw.ts) can both open, and only one of them sends at a time.
 */
import { reportsUrl } from './api'

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

/**
 * What the reports need from the phone's storage. In the browser this is IndexedDB
 * (reportStore.ts); each queued report is its own record, so adding one while another is
 * removed cannot lose either.
 */
export interface ReportStore {
  getValue(key: string): Promise<string | null>
  setValue(key: string, value: string): Promise<void>
  /** Every queued record, oldest first, unchecked. */
  listQueued(): Promise<unknown[]>
  addQueued(item: QueuedReport): Promise<void>
  removeQueued(id: string): Promise<void>
}

/** The part of localStorage that part 1 used, read once to move its data. */
export interface LegacyStore {
  getItem(key: string): string | null
  removeItem(key: string): void
}

/** The part of the Web Locks API (navigator.locks) the sender needs. */
export interface LockManagerLike {
  request<T>(name: string, callback: () => Promise<T>): Promise<T>
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
const SEND_LOCK = 'signal.sendReports'
const VISITOR_ID = /^[0-9a-f]{32}$/
const HOUR_MS = 3_600_000
// The report API refuses a report hour more than 48 hours before it arrives (ADR 0026).
const MAX_REPORT_AGE_MS = 48 * HOUR_MS
const TOO_OLD = 'A saved report was more than 48 hours old, so it was not sent.'
const REFUSED = 'The report was not accepted.'

/** A store that lasts only while the page is open, for a browser without IndexedDB. */
export function memoryReportStore(): ReportStore {
  const values = new Map<string, string>()
  let queued: QueuedReport[] = []
  return {
    getValue: async (key) => values.get(key) ?? null,
    setValue: async (key, value) => void values.set(key, value),
    listQueued: async () => [...queued],
    addQueued: async (item) => void queued.push(item),
    removeQueued: async (id) => {
      queued = queued.filter((item) => item.id !== id)
    },
  }
}

/** Return the phone's visitor ID, creating it the first time: 16 random bytes as hexadecimal. */
export async function getOrCreateVisitorId(
  store: ReportStore,
  randomBytes: (length: number) => Uint8Array,
): Promise<string> {
  const stored = await store.getValue(KEYS.visitorId)
  if (stored !== null && VISITOR_ID.test(stored)) return stored
  const id = Array.from(randomBytes(16), (byte) => byte.toString(16).padStart(2, '0')).join('')
  await store.setValue(KEYS.visitorId, id)
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

/** The reports waiting on the phone, oldest first. Damaged records are skipped. */
export async function loadQueue(store: ReportStore): Promise<QueuedReport[]> {
  return (await store.listQueued()).filter(isQueuedReport)
}

/** Add a report to the queue and return how many now wait. */
export async function enqueueReport(store: ReportStore, report: ReportIn, id: string): Promise<number> {
  await store.addQueued({ id, report })
  return (await loadQueue(store)).length
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
  store: ReportStore,
  send: (report: ReportIn) => Promise<SendResult>,
  now: Date,
): Promise<FlushSummary> {
  const summary: FlushSummary = { accepted: 0, refused: [], waiting: 0 }
  for (const item of await loadQueue(store)) {
    if (now.getTime() - Date.parse(item.report.report_hour_utc) > MAX_REPORT_AGE_MS) {
      await store.removeQueued(item.id)
      summary.refused.push(TOO_OLD)
      continue
    }
    const result = await send(item.report)
    if (result.kind === 'retry') break
    await store.removeQueued(item.id)
    if (result.kind === 'accepted') summary.accepted += 1
    else summary.refused.push(result.message)
  }
  summary.waiting = (await loadQueue(store)).length
  return summary
}

/**
 * Run one send at a time across the page and the background sender, so a report is never
 * posted twice. A browser without Web Locks has no service worker either, so only the page sends.
 */
export async function withSendLock<T>(
  locks: LockManagerLike | undefined,
  send: () => Promise<T>,
): Promise<T> {
  return locks === undefined ? send() : locks.request(SEND_LOCK, send)
}

/** Everything the page and the background sender share to send the queue. */
export async function sendWaitingReports(deps: {
  store: ReportStore
  locks: LockManagerLike | undefined
  fetchImpl: typeof fetch
  apiBaseUrl: string
  now: Date
}): Promise<FlushSummary> {
  return withSendLock(deps.locks, async () => {
    const visitorId = await getOrCreateVisitorId(deps.store, (length) =>
      crypto.getRandomValues(new Uint8Array(length)),
    )
    const url = reportsUrl(deps.apiBaseUrl)
    return flushQueue(deps.store, (report) => sendReport(url, visitorId, report, deps.fetchImpl), deps.now)
  })
}

function readOldQueue(local: LegacyStore): QueuedReport[] {
  try {
    const parsed: unknown = JSON.parse(local.getItem(KEYS.queue) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter(isQueuedReport) : []
  } catch {
    return []
  }
}

/**
 * Move part 1's data out of localStorage, which a service worker cannot read. A visitor ID the
 * store already has wins, so a phone keeps one ID. The old keys are removed, so this runs once.
 */
export async function moveFromLocalStorage(local: LegacyStore, store: ReportStore): Promise<void> {
  const oldId = local.getItem(KEYS.visitorId)
  if (oldId !== null && VISITOR_ID.test(oldId) && (await store.getValue(KEYS.visitorId)) === null) {
    await store.setValue(KEYS.visitorId, oldId)
  }
  const oldCarrier = local.getItem(KEYS.carrier)
  if (oldCarrier !== null) await store.setValue(KEYS.carrier, oldCarrier)
  for (const item of readOldQueue(local)) await store.addQueued(item)
  for (const key of Object.values(KEYS)) local.removeItem(key)
}

export async function loadCarrier(store: ReportStore): Promise<Carrier | null> {
  const stored = await store.getValue(KEYS.carrier)
  return CARRIERS.find((carrier) => carrier === stored) ?? null
}

export async function saveCarrier(store: ReportStore, carrier: Carrier): Promise<void> {
  await store.setValue(KEYS.carrier, carrier)
}

/** "1 report waiting to send", "3 reports waiting to send", or nothing. */
export function waitingNote(count: number): string {
  if (count === 0) return ''
  return `${count} ${count === 1 ? 'report' : 'reports'} waiting to send`
}
