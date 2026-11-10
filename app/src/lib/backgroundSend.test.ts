import { describe, it, expect } from 'vitest'
import {
  SYNC_TAG,
  WORKER_URL,
  askForBackgroundSend,
  handleSync,
  registerReportWorker,
  type WorkerContainerLike,
} from './backgroundSend'
import type { FlushSummary } from './reports'

function container(options: { sync: boolean; failRegister?: boolean }): WorkerContainerLike & {
  registered: string[]
  syncTags: string[]
} {
  const registered: string[] = []
  const syncTags: string[] = []
  const registration = options.sync
    ? { sync: { register: async (tag: string) => void syncTags.push(tag) } }
    : {}
  return {
    registered,
    syncTags,
    register: async (url: string) => {
      if (options.failRegister) throw new Error('blocked')
      registered.push(url)
      return registration
    },
    ready: Promise.resolve(registration),
  }
}

describe('installing the report sender', () => {
  it('registers the worker from this site', async () => {
    const browser = container({ sync: true })
    expect(await registerReportWorker(browser)).toBe(true)
    expect(browser.registered).toEqual([WORKER_URL])
    expect(WORKER_URL).toBe('/sw.js')
  })

  it('leaves the page working when the browser has no service workers', async () => {
    expect(await registerReportWorker(undefined)).toBe(false)
  })

  it('leaves the page working when registering fails', async () => {
    expect(await registerReportWorker(container({ sync: true, failRegister: true }))).toBe(false)
  })
})

describe('asking for a background send (FR-52)', () => {
  it('asks the browser to send when signal returns, where it can (Android)', async () => {
    const browser = container({ sync: true })
    expect(await askForBackgroundSend(browser)).toBe(true)
    expect(browser.syncTags).toEqual([SYNC_TAG])
  })

  it('says no where the browser cannot (iPhone), so the page sends next time it opens', async () => {
    expect(await askForBackgroundSend(container({ sync: false }))).toBe(false)
    expect(await askForBackgroundSend(undefined)).toBe(false)
  })
})

describe('the background send', () => {
  const done: FlushSummary = { accepted: 1, refused: [], waiting: 0 }
  const stillWaiting: FlushSummary = { accepted: 0, refused: [], waiting: 1 }

  it('sends the waiting reports when the browser says signal is back', async () => {
    let sends = 0
    await handleSync(SYNC_TAG, async () => {
      sends += 1
      return done
    })
    expect(sends).toBe(1)
  })

  it('ignores other background jobs', async () => {
    let sends = 0
    await handleSync('something-else', async () => {
      sends += 1
      return done
    })
    expect(sends).toBe(0)
  })

  it('fails when reports still wait, so the browser tries again later', async () => {
    await expect(handleSync(SYNC_TAG, async () => stillWaiting)).rejects.toThrow(/waiting/)
  })
})
