/**
 * The report sender (C21 part 2), served as /sw.js. It only sends saved reports when the browser
 * says signal is back; it does not cache pages or answer requests. Built on its own by
 * vite.sw.config.ts into one classic script, because module service workers are not supported
 * everywhere.
 */
import { handleSync } from './lib/backgroundSend'
import { openReportStore } from './lib/reportStore'
import { sendWaitingReports } from './lib/reports'

// The service worker types live in TypeScript's WebWorker library, which cannot be mixed with the
// DOM library the rest of the site uses, so the few parts needed are written out here.
interface ExtendableEventLike extends Event {
  waitUntil(work: Promise<unknown>): void
}
interface SyncEventLike extends ExtendableEventLike {
  tag: string
}
interface WorkerScope {
  skipWaiting(): Promise<void>
  clients: { claim(): Promise<void> }
  addEventListener(type: 'install' | 'activate', listener: (event: ExtendableEventLike) => void): void
  addEventListener(type: 'sync', listener: (event: SyncEventLike) => void): void
}

const worker = self as unknown as WorkerScope

// A new version takes over at once, so a fix to the sender reaches phones on their next visit.
worker.addEventListener('install', (event) => event.waitUntil(worker.skipWaiting()))
worker.addEventListener('activate', (event) => event.waitUntil(worker.clients.claim()))

worker.addEventListener('sync', (event) => {
  event.waitUntil(
    handleSync(event.tag, async () =>
      sendWaitingReports({
        store: await openReportStore(indexedDB),
        locks: navigator.locks,
        fetchImpl: fetch,
        apiBaseUrl: import.meta.env.VITE_API_BASE_URL,
        now: new Date(),
      }),
    ),
  )
})
