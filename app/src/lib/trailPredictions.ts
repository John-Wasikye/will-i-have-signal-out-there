import { isRunLate, type TrailSignal } from './trailSignal'

export type PredictionsLoad =
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'ready'; signal: Pick<TrailSignal, 'last_good_run_utc' | 'valid_until_utc'> }

export type PredictionsCard =
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'ready'; state: 'ok' | 'late'; lastGoodRunUtc: string; validUntilUtc: string }

/**
 * What the trail predictions card shows. The trail answer says when the predictions stop being
 * valid, so the card can be working or running late, but it cannot tell a failed run, so it has
 * no failed state.
 */
export function predictionsCard(load: PredictionsLoad, now: Date): PredictionsCard {
  if (load.kind !== 'ready') return { kind: load.kind }
  const { last_good_run_utc: lastGoodRunUtc, valid_until_utc: validUntilUtc } = load.signal
  return {
    kind: 'ready',
    state: isRunLate(validUntilUtc, now) ? 'late' : 'ok',
    lastGoodRunUtc,
    validUntilUtc,
  }
}
