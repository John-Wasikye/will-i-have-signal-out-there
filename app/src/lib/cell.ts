/**
 * Turning a position into an H3 cell (ADR 0009). h3-js is large and used only when a hiker taps a
 * report button, so this file is its own chunk. ReportButtons starts loading it as soon as the page
 * opens, while there is still signal, so a tap later works offline.
 */
import { latLngToCell } from 'h3-js'

const CELL_RESOLUTION = 9

/** Turn a position into its H3 resolution 9 cell. Only the cell leaves this function. */
export function captureCell(position: { coords: { latitude: number; longitude: number } }): string {
  return latLngToCell(position.coords.latitude, position.coords.longitude, CELL_RESOLUTION)
}
