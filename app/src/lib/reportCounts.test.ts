import { describe, it, expect } from 'vitest'
import { carrierTotals, type ReportCount } from './reportCounts'

function count(area: string, carrier: string, hadSignal: boolean, n: number): ReportCount {
  return { area_id: area, carrier, had_signal: hadSignal, report_count: n }
}

describe('carrierTotals', () => {
  it('adds up each carrier over the areas along the trail', () => {
    const counts = [
      count('a', 'T-Mobile', true, 3),
      count('b', 'T-Mobile', true, 2),
      count('b', 'T-Mobile', false, 1),
    ]
    expect(carrierTotals(counts)).toEqual([{ carrier: 'T-Mobile', withSignal: 5, withoutSignal: 1 }])
  })

  it('lists the carriers in name order', () => {
    const counts = [count('a', 'Verizon', false, 2), count('a', 'AT&T', true, 4)]
    expect(carrierTotals(counts).map((total) => total.carrier)).toEqual(['AT&T', 'Verizon'])
  })

  it('has nothing to list when no area has enough reports', () => {
    expect(carrierTotals([])).toEqual([])
  })
})
