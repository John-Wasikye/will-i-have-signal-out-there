import { DATA_SOURCES } from '../lib/sources'

export function Credits() {
  return (
    <section className="panel" aria-labelledby="credits-heading">
      <h2 id="credits-heading">Data sources and credits</h2>
      <ul>
        {DATA_SOURCES.map((source) => (
          <li key={source.name}>{source.credit}</li>
        ))}
      </ul>
    </section>
  )
}
