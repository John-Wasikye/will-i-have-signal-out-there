import { describe, it, expect } from 'vitest'
import { DATA_SOURCES } from './sources'

describe('DATA_SOURCES', () => {
  it('names the five data sources', () => {
    expect(DATA_SOURCES.map((source) => source.name)).toEqual([
      'CelesTrak',
      'National Park Service',
      'Federal Communications Commission (FCC)',
      'Copernicus',
      'Ookla',
    ])
  })

  it('gives each source its decided credit line (ADR 0037, Ookla ADR 0013)', () => {
    expect(DATA_SOURCES.map((source) => source.credit)).toEqual([
      'Orbital data: CelesTrak (celestrak.org), maintained by Dr. T.S. Kelso.',
      'Trail data: National Park Service.',
      'Coverage data: FCC National Broadband Map (broadbandmap.fcc.gov).',
      'Terrain produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.',
      'Includes data derived from Speedtest by Ookla® open data, licensed under CC BY-NC-SA 4.0. Derived data published here is shared under the same license.',
    ])
  })
})
