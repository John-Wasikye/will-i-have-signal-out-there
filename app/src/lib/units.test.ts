import { describe, it, expect } from 'vitest'
import { formatAreaWidth, formatDistance, formatElevation, toFeet, toMiles } from './units'

describe('toFeet', () => {
  it('converts meters to whole feet', () => {
    expect(toFeet(1000)).toBe(3281)
  })
})

describe('toMiles', () => {
  it('converts kilometers to miles', () => {
    expect(toMiles(1)).toBeCloseTo(0.621371)
    expect(toMiles(0)).toBe(0)
  })
})

describe('formatElevation', () => {
  it('shows meters with feet in brackets and thousands separators', () => {
    expect(formatElevation(2087)).toBe('2,087 m (6,847 ft)')
  })
})

describe('formatDistance', () => {
  it('shows kilometers with miles in brackets, both to two decimals', () => {
    expect(formatDistance(0)).toBe('0.00 km (0.00 mi)')
    expect(formatDistance(12.75)).toBe('12.75 km (7.92 mi)')
  })
})

describe('formatAreaWidth', () => {
  it('shows meters with feet in brackets, the feet to the nearest 10 because the width is approximate', () => {
    expect(formatAreaWidth(350)).toBe('350 m (1,150 ft)')
    expect(formatAreaWidth(100)).toBe('100 m (330 ft)')
  })
})
