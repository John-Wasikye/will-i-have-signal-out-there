/**
 * Sending saved reports in the background (C21 part 2, FR-52).
 *
 * The page installs a small service worker (src/sw.ts, served as /sw.js). After saving a report,
 * the page asks the browser for a background sync. Chrome on Android then wakes the worker when
 * the phone has signal again, even with the page closed. Browsers without background sync (Safari
 * on iPhone) keep part 1's behavior: the page sends the next time it is open.
 */
import type { FlushSummary } from './reports'

export const SYNC_TAG = 'send-reports'
export const WORKER_URL = '/sw.js'

interface RegistrationLike {
  sync?: { register(tag: string): Promise<void> }
}

/** The part of navigator.serviceWorker the page needs, so tests can pass a plain object. */
export interface WorkerContainerLike {
  register(url: string): Promise<unknown>
  ready: Promise<unknown>
}

/** Install the worker. A browser that refuses still sends from the page, so this never throws. */
export async function registerReportWorker(container: WorkerContainerLike | undefined): Promise<boolean> {
  if (container === undefined) return false
  try {
    await container.register(WORKER_URL)
    return true
  } catch {
    return false
  }
}

/** Ask for a send when signal returns. False means the page must send it itself. */
export async function askForBackgroundSend(container: WorkerContainerLike | undefined): Promise<boolean> {
  if (container === undefined) return false
  try {
    const registration = (await container.ready) as RegistrationLike
    if (registration.sync === undefined) return false
    await registration.sync.register(SYNC_TAG)
    return true
  } catch {
    return false
  }
}

/**
 * The worker's answer to a sync event. It fails while reports still wait, because a failed sync
 * is how the browser knows to try again later.
 */
export async function handleSync(tag: string, sendWaiting: () => Promise<FlushSummary>): Promise<void> {
  if (tag !== SYNC_TAG) return
  const summary = await sendWaiting()
  if (summary.waiting > 0) {
    throw new Error(`${summary.waiting} reports still waiting; the browser will try again.`)
  }
}
