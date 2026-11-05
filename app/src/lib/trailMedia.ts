import { TRAIL_ELEVATIONS_M } from './trailElevations'
import type { MapPoint } from './trailSignal'

const FEET_PER_METER = 3.28084

export interface TrailTerrain {
  imageUrl: string
  elevationsM: number[]
}

export interface TrailPhoto {
  url: string
  alt: string
  credit: string
  sourceUrl: string
}

const PHOTOS: Record<string, Omit<TrailPhoto, 'url'>> = {
  'grca-bright-angel': {
    alt: 'Two riders on mules on the Bright Angel Trail, with red canyon walls behind them.',
    credit: 'Photo: Grand Canyon National Park, public domain',
    sourceUrl:
      'https://commons.wikimedia.org/wiki/File:Grand_Canyon_National_Park,_Bright_Angel_Trial,_Mule_Trip_4825_-_Flickr_-_Grand_Canyon_NPS.jpg',
  },
  'grca-south-kaibab': {
    alt: 'Hikers on a stone-walled bend of the South Kaibab Trail, below a tall red rock tower.',
    credit: 'Photo: Grand Canyon National Park, public domain',
    sourceUrl:
      'https://commons.wikimedia.org/wiki/File:Grand_Canyon_National_Park-_South_Kaibab_Trail-_2786_-_48894676057.jpg',
  },
  'grca-north-kaibab': {
    alt: 'The North Kaibab Trail running between high red walls in the inner canyon.',
    credit: 'Photo: Grand Canyon National Park, CC BY 2.0',
    sourceUrl:
      'https://commons.wikimedia.org/wiki/File:Inner_Canyon,_Grand_Canyon_National_Park_-_North_Kaibab_Trail_1143_(6894082540).jpg',
  },
}

export const PHASE_A_TRAIL_IDS = Object.keys(PHOTOS)

/** The picture and heights were drawn for one version of a trail, so they must match its points. */
export function terrainFor(trailId: string, pointCount: number): TrailTerrain | undefined {
  const elevationsM = TRAIL_ELEVATIONS_M[trailId]
  if (elevationsM?.length !== pointCount) return undefined
  return { imageUrl: `/trails/${trailId}-terrain.png`, elevationsM }
}

export function photoFor(trailId: string): TrailPhoto | undefined {
  const photo = PHOTOS[trailId]
  return photo && { ...photo, url: `/trails/${trailId}.jpg` }
}

/** Fits a list of heights into a chart, with the highest ground at the top. */
export function profileLine(heights: number[], width: number, height: number): MapPoint[] {
  const low = Math.min(...heights)
  const span = Math.max(...heights) - low || 1
  return heights.map((value, index) => ({
    x: (index / Math.max(heights.length - 1, 1)) * width,
    y: height - ((value - low) / span) * height,
  }))
}

export function toFeet(meters: number): number {
  return Math.round(meters * FEET_PER_METER)
}
