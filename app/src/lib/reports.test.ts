import { cellToLatLng, getResolution, isValidCell, latLngToCell } from 'h3-js'
import { describe, it, expect } from 'vitest'
import serverCode from '../../../platform/serving/reports.py?raw'
import { captureCell } from './cell'
import {
  CARRIERS,
  buildReport,
  enqueueReport,
  flushQueue,
  getOrCreateVisitorId,
  loadCarrier,
  loadQueue,
  memoryReportStore,
  moveFromLocalStorage,
  reportHourUtc,
  saveCarrier,
  sendReport,
  sendWaitingReports,
  waitingNote,
  withSendLock,
  type LegacyStore,
  type LockManagerLike,
  type QueuedReport,
  type ReportIn,
  type SendResult,
} from './reports'

/** Storage that behaves like localStorage: strings in, strings out. */
function legacyStore(initial: Record<string, string> = {}): LegacyStore & {
  data: Record<string, string>
} {
  const data = { ...initial }
  return {
    data,
    getItem: (key) => (key in data ? data[key] : null),
    removeItem: (key) => {
      delete data[key]
    },
  }
}

const SOUTH_RIM = { coords: { latitude: 36.0579, longitude: -112.143 } }
const NOW = new Date('2026-11-09T18:42:31.250Z')

function report(overrides: Partial<ReportIn> = {}): ReportIn {
  return {
    cell: latLngToCell(36.0579, -112.143, 9),
    carrier: 'T-Mobile',
    had_signal: true,
    report_hour_utc: '2026-11-09T18:00:00Z',
    ...overrides,
  }
}

describe('the visitor ID', () => {
  const bytes = (n: number) => Uint8Array.from({ length: n }, (_, i) => i * 17)

  it('is 16 random bytes written as 32 lowercase hexadecimal characters (ADR 0025)', async () => {
    const id = await getOrCreateVisitorId(memoryReportStore(), bytes)
    expect(id).toMatch(/^[0-9a-f]{32}$/)
    expect(id.startsWith('00112233')).toBe(true)
  })

  it('is created once and kept on the phone', async () => {
    const store = memoryReportStore()
    const first = await getOrCreateVisitorId(store, bytes)
    const second = await getOrCreateVisitorId(store, () => new Uint8Array(16).fill(255))
    expect(second).toBe(first)
  })

  it('is replaced when the stored value is damaged', async () => {
    const store = memoryReportStore()
    await store.setValue('signal.visitorId', 'not-an-id')
    expect(await getOrCreateVisitorId(store, bytes)).toMatch(/^[0-9a-f]{32}$/)
  })
})

describe('the report', () => {
  it('rounds the time down to the hour, in UTC', () => {
    expect(reportHourUtc(NOW)).toBe('2026-11-09T18:00:00Z')
    expect(reportHourUtc(new Date('2026-11-09T23:59:59-07:00'))).toBe('2026-11-10T06:00:00Z')
  })

  it('turns the position into an H3 resolution 9 cell (ADR 0009)', () => {
    const cell = captureCell(SOUTH_RIM)
    expect(isValidCell(cell)).toBe(true)
    expect(getResolution(cell)).toBe(9)
    expect(cell).toBe(latLngToCell(36.0579, -112.143, 9))
  })

  it('keeps the cell close to the position, so it is the right place', () => {
    const [lat, lng] = cellToLatLng(captureCell(SOUTH_RIM))
    expect(Math.abs(lat - 36.0579)).toBeLessThan(0.005)
    expect(Math.abs(lng + 112.143)).toBeLessThan(0.005)
  })

  it('holds only the cell, carrier, signal and hour', () => {
    const built = buildReport(captureCell(SOUTH_RIM), 'Verizon', false, NOW)
    expect(built).toEqual({
      cell: latLngToCell(36.0579, -112.143, 9),
      carrier: 'Verizon',
      had_signal: false,
      report_hour_utc: '2026-11-09T18:00:00Z',
    })
  })
})

describe('sending one report', () => {
  function capture(status: number, body: unknown = {}) {
    const calls: { url: string; init: RequestInit }[] = []
    const fetchImpl = (async (url: string, init: RequestInit) => {
      calls.push({ url, init })
      return new Response(JSON.stringify(body), { status })
    }) as unknown as typeof fetch
    return { calls, fetchImpl }
  }

  it('posts only the four report fields, with the visitor ID in a header (QR-10)', async () => {
    const { calls, fetchImpl } = capture(202, { status: 'accepted' })
    const visitorId = '0123456789abcdef0123456789abcdef'

    await sendReport('https://api.example.com/reports', visitorId, report(), fetchImpl)

    const [{ url, init }] = calls
    expect(url).toBe('https://api.example.com/reports')
    expect(init.method).toBe('POST')
    const sent = JSON.parse(String(init.body))
    expect(Object.keys(sent).sort()).toEqual(['carrier', 'cell', 'had_signal', 'report_hour_utc'])
    expect(String(init.body)).not.toMatch(/36\.05|112\.14|latitude|longitude/)
    expect(String(init.body)).not.toContain(visitorId)
    const headers = new Headers(init.headers)
    expect(headers.get('x-visitor-id')).toBe(visitorId)
    expect(headers.get('content-type')).toBe('application/json')
  })

  it('reads 202 as accepted', async () => {
    const { fetchImpl } = capture(202, { status: 'accepted' })
    expect(await sendReport('u', 'v', report(), fetchImpl)).toEqual({ kind: 'accepted' })
  })

  it.each([400, 429])('reads %i as refused and keeps the server message', async (status) => {
    const { fetchImpl } = capture(status, { error: { code: 'x', message: 'Why it was refused.' } })
    expect(await sendReport('u', 'v', report(), fetchImpl)).toEqual({
      kind: 'refused',
      message: 'Why it was refused.',
    })
  })

  it.each([500, 502, 503])('reads %i as try again later', async (status) => {
    const { fetchImpl } = capture(status)
    expect(await sendReport('u', 'v', report(), fetchImpl)).toEqual({ kind: 'retry' })
  })

  it('reads a network failure as try again later', async () => {
    const offline = (async () => {
      throw new TypeError('Failed to fetch')
    }) as unknown as typeof fetch
    expect(await sendReport('u', 'v', report(), offline)).toEqual({ kind: 'retry' })
  })

  it('gives a plain message when a refusal has no readable body', async () => {
    const { fetchImpl } = capture(429, 'not json')
    const result = await sendReport('u', 'v', report(), fetchImpl)
    expect(result.kind).toBe('refused')
  })
})

describe('the queue on the phone (ADR 0010)', () => {
  it('keeps reports in the order they were saved', async () => {
    const store = memoryReportStore()
    expect(await enqueueReport(store, report(), 'a')).toBe(1)
    expect(await enqueueReport(store, report({ had_signal: false }), 'b')).toBe(2)

    expect((await loadQueue(store)).map((item) => item.id)).toEqual(['a', 'b'])
  })

  it('skips a damaged saved report', async () => {
    const store = memoryReportStore()
    await store.addQueued({ id: 'damaged' } as unknown as QueuedReport)
    await enqueueReport(store, report(), 'good')
    expect((await loadQueue(store)).map((item) => item.id)).toEqual(['good'])
  })

  it('sends every waiting report and empties the queue when all are accepted', async () => {
    const store = memoryReportStore()
    await enqueueReport(store, report(), 'a')
    await enqueueReport(store, report({ had_signal: false }), 'b')
    const sent: ReportIn[] = []

    const summary = await flushQueue(
      store,
      async (r) => {
        sent.push(r)
        return { kind: 'accepted' }
      },
      NOW,
    )

    expect(sent).toHaveLength(2)
    expect(summary).toEqual({ accepted: 2, refused: [], waiting: 0 })
    expect(await loadQueue(store)).toEqual([])
  })

  it('keeps reports that could not be sent, and stops trying until later', async () => {
    const store = memoryReportStore()
    await enqueueReport(store, report(), 'a')
    await enqueueReport(store, report({ had_signal: false }), 'b')
    let calls = 0

    const summary = await flushQueue(
      store,
      async () => {
        calls += 1
        return { kind: 'retry' }
      },
      NOW,
    )

    expect(calls).toBe(1)
    expect(summary).toEqual({ accepted: 0, refused: [], waiting: 2 })
    expect((await loadQueue(store)).map((item) => item.id)).toEqual(['a', 'b'])
  })

  it('drops a refused report, because sending it again cannot succeed', async () => {
    const store = memoryReportStore()
    await enqueueReport(store, report(), 'a')
    await enqueueReport(store, report({ had_signal: false }), 'b')
    const answers: SendResult[] = [
      { kind: 'refused', message: 'You already reported this same place within 24 hours.' },
      { kind: 'accepted' },
    ]

    const summary = await flushQueue(store, async () => answers.shift()!, NOW)

    expect(summary).toEqual({
      accepted: 1,
      refused: ['You already reported this same place within 24 hours.'],
      waiting: 0,
    })
    expect(await loadQueue(store)).toEqual([])
  })

  it('drops reports more than 48 hours old without sending them (ADR 0026)', async () => {
    const store = memoryReportStore()
    await enqueueReport(store, report({ report_hour_utc: '2026-11-07T18:00:00Z' }), 'old')
    await enqueueReport(store, report({ report_hour_utc: '2026-11-07T19:00:00Z' }), 'kept')
    const sent: string[] = []

    const summary = await flushQueue(
      store,
      async (r) => {
        sent.push(r.report_hour_utc)
        return { kind: 'accepted' }
      },
      NOW,
    )

    expect(sent).toEqual(['2026-11-07T19:00:00Z'])
    expect(summary.refused).toHaveLength(1)
    expect(summary.refused[0]).toContain('48 hours')
  })

  it('keeps a report added while the queue is being sent', async () => {
    const store = memoryReportStore()
    await enqueueReport(store, report(), 'a')

    await flushQueue(
      store,
      async () => {
        await enqueueReport(store, report({ had_signal: false }), 'added-meanwhile')
        return { kind: 'accepted' }
      },
      NOW,
    )

    expect((await loadQueue(store)).map((item) => item.id)).toEqual(['added-meanwhile'])
  })
})

describe('moving from localStorage (part 1) to the shared store (part 2)', () => {
  const OLD_ID = '0123456789abcdef0123456789abcdef'
  const oldQueue = JSON.stringify([
    { id: 'a', report: report() },
    { id: 'b', report: report({ had_signal: false }) },
  ])

  it('moves the visitor ID, carrier and waiting reports, then clears localStorage', async () => {
    const local = legacyStore({
      'signal.visitorId': OLD_ID,
      'signal.carrier': 'Verizon',
      'signal.reportQueue': oldQueue,
    })
    const store = memoryReportStore()

    await moveFromLocalStorage(local, store)

    expect(await getOrCreateVisitorId(store, () => new Uint8Array(16))).toBe(OLD_ID)
    expect(await loadCarrier(store)).toBe('Verizon')
    expect((await loadQueue(store)).map((item) => item.id)).toEqual(['a', 'b'])
    expect(local.data).toEqual({})
  })

  it('keeps a visitor ID the shared store already has', async () => {
    const store = memoryReportStore()
    const kept = await getOrCreateVisitorId(store, () => new Uint8Array(16).fill(7))
    await moveFromLocalStorage(legacyStore({ 'signal.visitorId': OLD_ID }), store)
    expect(await getOrCreateVisitorId(store, () => new Uint8Array(16))).toBe(kept)
  })

  it('does nothing the second time', async () => {
    const local = legacyStore({ 'signal.reportQueue': oldQueue })
    const store = memoryReportStore()
    await moveFromLocalStorage(local, store)
    await moveFromLocalStorage(local, store)
    expect(await loadQueue(store)).toHaveLength(2)
  })

  it('skips damaged old data', async () => {
    const local = legacyStore({ 'signal.reportQueue': '{oops', 'signal.visitorId': 'bad' })
    const store = memoryReportStore()
    await moveFromLocalStorage(local, store)
    expect(await loadQueue(store)).toEqual([])
    expect(await store.getValue('signal.visitorId')).toBeNull()
    expect(local.data).toEqual({})
  })
})

describe('one sender at a time', () => {
  function fakeLocks(): LockManagerLike & { names: string[] } {
    const names: string[] = []
    let tail: Promise<unknown> = Promise.resolve()
    return {
      names,
      request: (name, callback) => {
        names.push(name)
        const run = tail.then(() => callback())
        tail = run.catch(() => undefined)
        return run
      },
    }
  }

  it('lets the page and the background sender take turns', async () => {
    const locks = fakeLocks()
    const order: string[] = []
    let release!: () => void
    const first = withSendLock(locks, async () => {
      order.push('first starts')
      await new Promise<void>((resolve) => (release = resolve))
      order.push('first ends')
    })
    const second = withSendLock(locks, async () => {
      order.push('second')
    })
    await Promise.resolve()
    release()
    await Promise.all([first, second])

    expect(order).toEqual(['first starts', 'first ends', 'second'])
    expect(new Set(locks.names).size).toBe(1)
  })

  it('still sends when the browser has no locks', async () => {
    expect(await withSendLock(undefined, async () => 'sent')).toBe('sent')
  })
})

describe('sending the waiting reports', () => {
  it('sends each one with the stored visitor ID to the report address', async () => {
    const store = memoryReportStore()
    const visitorId = await getOrCreateVisitorId(store, () => new Uint8Array(16).fill(1))
    await enqueueReport(store, report(), 'a')
    const calls: { url: string; init: RequestInit }[] = []
    const fetchImpl = (async (url: string, init: RequestInit) => {
      calls.push({ url, init })
      return new Response('{}', { status: 202 })
    }) as unknown as typeof fetch

    const summary = await sendWaitingReports({
      store,
      locks: undefined,
      fetchImpl,
      apiBaseUrl: 'https://api.example.com/',
      now: NOW,
    })

    expect(summary).toEqual({ accepted: 1, refused: [], waiting: 0 })
    expect(calls).toHaveLength(1)
    expect(calls[0].url).toBe('https://api.example.com/reports')
    expect(new Headers(calls[0].init.headers).get('x-visitor-id')).toBe(visitorId)
  })
})

describe('the carrier', () => {
  it('is remembered on the phone', async () => {
    const store = memoryReportStore()
    expect(await loadCarrier(store)).toBeNull()
    await saveCarrier(store, 'AT&T')
    expect(await loadCarrier(store)).toBe('AT&T')
  })

  it('ignores a stored value that is not on the list', async () => {
    const store = memoryReportStore()
    await store.setValue('signal.carrier', 'Acme')
    expect(await loadCarrier(store)).toBeNull()
  })

  it('offers exactly the carriers the report API accepts', () => {
    const listed = serverCode.match(/CARRIERS = frozenset\(\{([^}]*)\}\)/)
    expect(listed).not.toBeNull()
    const server = [...listed![1].matchAll(/"([^"]+)"/g)].map((m) => m[1]).sort()
    expect([...CARRIERS].sort()).toEqual(server)
  })
})

describe('the waiting note', () => {
  it('says how many reports wait, in plain words', () => {
    expect(waitingNote(0)).toBe('')
    expect(waitingNote(1)).toBe('1 report waiting to send')
    expect(waitingNote(3)).toBe('3 reports waiting to send')
  })
})
