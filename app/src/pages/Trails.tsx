import { Credits } from '../components/Credits'
import { DtcRequirementsNote } from '../components/DtcRequirementsNote'
import { PHASE_A_TRAILS } from '../lib/trails'

export function Trails() {
  return (
    <>
      <h1>Trails</h1>
      <p>
        Phase A, the first build stage, covers three main trails at Grand Canyon National Park. Coverage
        and satellite times for them are not ready yet, so this page lists only the trail names.
      </p>

      <ul className="cards">
        {PHASE_A_TRAILS.map((trail) => (
          <li key={trail} className="card">
            <h2>{trail}</h2>
            <p>Coverage and satellite times coming soon.</p>
          </li>
        ))}
      </ul>

      <DtcRequirementsNote />
      <Credits />
    </>
  )
}
