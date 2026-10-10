export type ProjectStatus = 'in-progress' | 'coming-soon'

export interface Project {
  number: number
  name: string
  description: string
  status: ProjectStatus
}

export const projects: Project[] = [
  {
    number: 1,
    name: 'Will I have signal out there?',
    description:
      'A trip planner for hikers that shows where phone carriers and satellite texting work along a route.',
    status: 'in-progress',
  },
  {
    number: 2,
    name: 'Asteroid Watch',
    description: 'A tracker for near-Earth asteroids and how close they pass to Earth.',
    status: 'coming-soon',
  },
  {
    number: 3,
    name: 'Ocean map',
    description: 'A map of ocean conditions, built from public measurements and shown on one page.',
    status: 'coming-soon',
  },
  {
    number: 4,
    name: 'Shooting star forecast',
    description: 'A nightly forecast of meteor shower activity and how good the viewing should be.',
    status: 'coming-soon',
  },
  {
    number: 5,
    name: 'Mission Control',
    description: 'A dashboard that brings the health of the platform pipelines into one place.',
    status: 'coming-soon',
  },
]
