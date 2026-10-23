const SIZE = 320
const DIVISIONS = 8

// Evenly spaced grid positions from 0 to SIZE.
const positions = Array.from({ length: DIVISIONS + 1 }, (_, i) => (i * SIZE) / DIVISIONS)

export function MapView() {
  return (
    <figure className="map">
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label="Placeholder map grid">
        <rect width={SIZE} height={SIZE} className="map-bg" />
        {positions.map((x) => (
          <line key={`v${x}`} x1={x} y1={0} x2={x} y2={SIZE} className="map-line" />
        ))}
        {positions.map((y) => (
          <line key={`h${y}`} x1={0} y1={y} x2={SIZE} y2={y} className="map-line" />
        ))}
      </svg>
      <figcaption>Map arrives in Project 1, Phase A</figcaption>
    </figure>
  )
}
