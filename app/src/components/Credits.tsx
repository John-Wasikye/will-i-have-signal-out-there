import { DATA_SOURCES } from '../lib/sources'

export function Credits() {
  return (
    <section aria-labelledby="credits-heading">
      <h2 id="credits-heading">Data sources and credits</h2>
      <p>The planner will draw on these sources. Full credits come with the live data.</p>
      <ul>
        {DATA_SOURCES.map((source) => (
          <li key={source.name}>
            <strong>{source.name}</strong>: {source.provides}
          </li>
        ))}
      </ul>
    </section>
  )
}
