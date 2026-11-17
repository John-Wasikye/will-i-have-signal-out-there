const STEPS = [
  { title: 'Public data', note: 'orbits, trails, coverage, terrain' },
  { title: 'Nightly job', note: 'Airflow, Spark' },
  { title: 'Data lake', note: 'Iceberg tables on S3' },
  { title: 'Checked marts and a publish gate', note: 'dbt, DuckDB' },
  { title: 'Small web service and this page', note: 'reads the published files' },
]

const BOX_WIDTH = 340
const BOX_HEIGHT = 56
const STRIDE = 84
const MARGIN = 8
const CENTER = 180

// The same words as the boxes, for people who cannot see the picture.
const DESCRIPTION =
  'How the planner is built, from top to bottom: public data (orbits, trails, coverage, terrain), ' +
  'then the nightly job (Airflow, Spark), then the data lake (Iceberg tables on S3), then checked ' +
  'marts (dbt, DuckDB) and a publish gate, then a small web service and this page.'

/** The path of the data from the public sources to the page, one box for each step. */
export function BuildDiagram() {
  return (
    <svg
      className="build-diagram"
      viewBox={`0 0 360 ${MARGIN * 2 + STRIDE * (STEPS.length - 1) + BOX_HEIGHT}`}
      role="img"
      aria-label={DESCRIPTION}
    >
      {STEPS.map((step, index) => {
        const top = MARGIN + index * STRIDE
        return (
          <g key={step.title}>
            <rect
              className="diagram-box"
              x={CENTER - BOX_WIDTH / 2}
              y={top}
              width={BOX_WIDTH}
              height={BOX_HEIGHT}
              rx={12}
            />
            <text className="diagram-title" x={CENTER} y={top + 24} textAnchor="middle">
              {step.title}
            </text>
            <text className="diagram-note" x={CENTER} y={top + 44} textAnchor="middle">
              {step.note}
            </text>
            {index < STEPS.length - 1 && (
              <path
                className="diagram-arrow"
                d={`M${CENTER} ${top + BOX_HEIGHT + 2} V${top + STRIDE - 4} M${CENTER - 6} ${top + STRIDE - 10} L${CENTER} ${top + STRIDE - 2} L${CENTER + 6} ${top + STRIDE - 10}`}
              />
            )}
          </g>
        )
      })}
    </svg>
  )
}
