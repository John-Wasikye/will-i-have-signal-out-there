import { ColdStartNotice } from './ColdStartNotice'

/**
 * Holds the place of the trail view while a trail loads. Without it the report section sits
 * under the trail buttons and the map pushes it down when the data arrives.
 */
export function TrailPlaceholder() {
  return (
    <div className="trail-placeholder">
      <ColdStartNotice />
    </div>
  )
}
