import { describe, it, expect } from 'vitest'
import { latestOnly } from './latestOnly'

describe('latestOnly', () => {
  it('keeps the answer to the newest request', () => {
    const begin = latestOnly()
    const isCurrent = begin()
    expect(isCurrent()).toBe(true)
  })

  it('drops the answer to an older request that arrives late', () => {
    const begin = latestOnly()
    const older = begin()
    const newer = begin()
    expect(older()).toBe(false)
    expect(newer()).toBe(true)
  })
})
