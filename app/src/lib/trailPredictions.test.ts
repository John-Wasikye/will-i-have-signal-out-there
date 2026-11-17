import { describe, it, expect } from 'vitest'
import { predictionsCard } from './trailPredictions'

const signal = { last_good_run_utc: '2026-11-05T10:01:00Z', valid_until_utc: '2026-11-06T12:00:00Z' }

describe('predictionsCard', () => {
  it('is working while the predictions are still valid', () => {
    expect(predictionsCard({ kind: 'ready', signal }, new Date('2026-11-06T11:59:00Z'))).toEqual({
      kind: 'ready',
      state: 'ok',
      lastGoodRunUtc: '2026-11-05T10:01:00Z',
      validUntilUtc: '2026-11-06T12:00:00Z',
    })
  })

  it('is still working at the valid until time itself, the same rule as the late notice', () => {
    expect(predictionsCard({ kind: 'ready', signal }, new Date('2026-11-06T12:00:00Z'))).toMatchObject({
      state: 'ok',
    })
  })

  it('is running late once the valid until time has passed', () => {
    expect(predictionsCard({ kind: 'ready', signal }, new Date('2026-11-06T12:00:01Z'))).toMatchObject({
      state: 'late',
    })
  })

  it('never says failed, because the trail answer cannot show that', () => {
    const states = ['2026-11-01T00:00:00Z', '2026-11-30T00:00:00Z'].map(
      (when) => predictionsCard({ kind: 'ready', signal }, new Date(when)),
    )
    for (const card of states) expect(card).not.toMatchObject({ state: 'failed' })
  })

  it('passes loading and error through, with no state', () => {
    expect(predictionsCard({ kind: 'loading' }, new Date())).toEqual({ kind: 'loading' })
    expect(predictionsCard({ kind: 'error' }, new Date())).toEqual({ kind: 'error' })
  })
})
