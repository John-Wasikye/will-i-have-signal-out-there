export interface DataSource {
  name: string
  credit: string
}

/** The data behind the page, with the credit lines decided in ADR 0037 (Ookla: ADR 0013). */
export const DATA_SOURCES: readonly DataSource[] = [
  {
    name: 'CelesTrak',
    credit: 'Orbital data: CelesTrak (celestrak.org), maintained by Dr. T.S. Kelso.',
  },
  { name: 'National Park Service', credit: 'Trail data: National Park Service.' },
  {
    name: 'Federal Communications Commission (FCC)',
    credit: 'Coverage data: FCC National Broadband Map (broadbandmap.fcc.gov).',
  },
  {
    name: 'Copernicus',
    credit:
      'Terrain produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.',
  },
  {
    name: 'Ookla',
    credit:
      'Includes data derived from Speedtest by Ookla® open data, licensed under CC BY-NC-SA 4.0. Derived data published here is shared under the same license.',
  },
]
