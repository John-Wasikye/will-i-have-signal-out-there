import { MapView } from '../components/MapView'
import { projects, type Project } from '../data/projects'

function statusLabel(project: Project): string {
  return project.status === 'in-progress' ? 'In progress: Phase A' : 'Coming soon'
}

export function Home() {
  return (
    <>
      <h1>Portfolio Data Platform</h1>
      <p>Five data projects, built one after another. Here is where each one stands.</p>

      <ul className="cards">
        {projects.map((project) => (
          <li key={project.number} className="card">
            <p className="card-number">Project {project.number}</p>
            <h2>{project.name}</h2>
            <p>{project.description}</p>
            <p className={project.status === 'in-progress' ? 'badge badge-active' : 'badge'}>
              {statusLabel(project)}
            </p>
          </li>
        ))}
      </ul>

      <section aria-labelledby="map-heading">
        <h2 id="map-heading">Map preview</h2>
        <MapView />
      </section>
    </>
  )
}
