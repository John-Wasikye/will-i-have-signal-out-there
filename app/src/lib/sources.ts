export interface DataSource {
  name: string
  provides: string
}

/** The data the planner plans to use. Full credits come with the live data. */
export const DATA_SOURCES: readonly DataSource[] = [
  { name: 'CelesTrak', provides: 'satellite orbits' },
  { name: 'National Park Service', provides: 'trail routes' },
  { name: 'Federal Communications Commission (FCC)', provides: 'mobile coverage' },
  { name: 'Copernicus', provides: 'elevation data' },
]
