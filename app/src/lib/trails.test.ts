import { describe, it, expect } from 'vitest'
import { PHASE_A_TRAILS } from './trails'

describe('PHASE_A_TRAILS', () => {
  it('lists the three main Grand Canyon trails in Phase A, by name only', () => {
    expect(PHASE_A_TRAILS).toEqual(['Bright Angel', 'South Kaibab', 'North Kaibab'])
  })
})
