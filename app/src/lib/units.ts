const FEET_PER_METER = 3.28084
const MILES_PER_KILOMETER = 0.621371

export function toFeet(meters: number): number {
  return Math.round(meters * FEET_PER_METER)
}

export function toMiles(kilometers: number): number {
  return kilometers * MILES_PER_KILOMETER
}

/** Meters first, because the trail data is metric, with feet in brackets for hikers in the US. */
export function formatElevation(meters: number): string {
  return `${meters.toLocaleString('en-US')} m (${toFeet(meters).toLocaleString('en-US')} ft)`
}

export function formatDistance(kilometers: number): string {
  return `${kilometers.toFixed(2)} km (${toMiles(kilometers).toFixed(2)} mi)`
}

/** For a width that is only approximate, so the feet are rounded to the nearest 10. */
export function formatAreaWidth(meters: number): string {
  const feet = Math.round((meters * FEET_PER_METER) / 10) * 10
  return `${meters.toLocaleString('en-US')} m (${feet.toLocaleString('en-US')} ft)`
}
