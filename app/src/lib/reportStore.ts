/**
 * The reports' store in IndexedDB, the browser database that both the page and the service
 * worker can open (localStorage is page-only). Two object stores: `values` for the visitor ID and
 * carrier, and `queue` for waiting reports, one record each, kept in the order they were added.
 *
 * Node has no IndexedDB, so this adapter is checked in a real browser; the logic that uses it is
 * tested in reports.test.ts against memoryReportStore.
 */
import { memoryReportStore, type QueuedReport, type ReportStore } from './reports'

const DATABASE = 'signal-reports'
const VERSION = 1
const VALUES = 'values'
const QUEUE = 'queue'
const BY_ID = 'byId'

function done<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

function finished(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(transaction.error)
    transaction.onabort = () => reject(transaction.error)
  })
}

function openDatabase(factory: IDBFactory): Promise<IDBDatabase> {
  const request = factory.open(DATABASE, VERSION)
  request.onupgradeneeded = () => {
    const database = request.result
    database.createObjectStore(VALUES)
    // An increasing key keeps the reports in the order they were added.
    const queue = database.createObjectStore(QUEUE, { autoIncrement: true })
    queue.createIndex(BY_ID, 'id', { unique: true })
  }
  return done(request)
}

function indexedDbStore(database: IDBDatabase): ReportStore {
  async function write(name: string, change: (store: IDBObjectStore) => void): Promise<void> {
    const transaction = database.transaction(name, 'readwrite')
    change(transaction.objectStore(name))
    await finished(transaction)
  }
  return {
    getValue: async (key) => {
      const value: unknown = await done(database.transaction(VALUES).objectStore(VALUES).get(key))
      return typeof value === 'string' ? value : null
    },
    setValue: (key, value) => write(VALUES, (store) => store.put(value, key)),
    listQueued: () => done(database.transaction(QUEUE).objectStore(QUEUE).getAll()),
    addQueued: (item: QueuedReport) => write(QUEUE, (store) => store.add(item)),
    removeQueued: (id) =>
      write(QUEUE, (store) => {
        const lookup = store.index(BY_ID).getKey(id)
        lookup.onsuccess = () => {
          if (lookup.result !== undefined) store.delete(lookup.result)
        }
      }),
  }
}

/**
 * Open the phone's report store. If IndexedDB is missing or refused (some private windows),
 * reports last only while the page is open, which is still better than not reporting.
 */
export async function openReportStore(factory: IDBFactory | undefined): Promise<ReportStore> {
  if (factory === undefined) return memoryReportStore()
  try {
    return indexedDbStore(await openDatabase(factory))
  } catch {
    return memoryReportStore()
  }
}
