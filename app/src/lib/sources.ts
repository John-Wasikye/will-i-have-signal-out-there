export interface DataSource {
  name: string
  credit: string
}

/**
 * The data behind the page, with the credit lines decided in ADR 0037 (Ookla: ADR 0013). The
 * OpenCellID line is the plain-text form from its attribution page, read Nov 17, 2026.
 */
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
  {
    name: 'OpenCellID',
    credit:
      'Cell tower data from OpenCellID (https://opencellid.org), licensed under CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/). Changes: cut to Arizona and matched to H3 cells.',
  },
]
