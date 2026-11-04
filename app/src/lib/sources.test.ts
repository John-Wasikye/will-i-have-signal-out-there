import { describe, it, expect } from 'vitest'
import { DATA_SOURCES } from './sources'

describe('DATA_SOURCES', () => {
  it('names the four planned data sources', () => {
    expect(DATA_SOURCES.map((source) => source.name)).toEqual([
      'CelesTrak',
      'National Park Service',
      'Federal Communications Commission (FCC)',
      'Copernicus',
    ])
  })

  it('says what each source provides', () => {
    for (const source of DATA_SOURCES) {
      expect(source.provides.length).toBeGreaterThan(0)
    }
  })
})
