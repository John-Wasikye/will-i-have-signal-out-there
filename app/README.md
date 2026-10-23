# Site

This is the public website for my trip planner, Will I have signal out there? It has a home page, a status page that shows whether the nightly data run is up to date, and a lookup page. I built it with Vite, React and TypeScript. It compiles to plain static files, so the site has no server of its own. Only the lookup page calls the API.

## Run it

Run these commands from this `app` folder:

- `npm install` installs the pinned versions.
- `npm run dev` starts the development server at http://localhost:5173.
- `npm run build` checks the types, then writes static files to `dist`.
- `npm run preview` serves the built `dist` folder on my machine.
- `npm test` runs the unit tests with Vitest.
- `npm run typecheck` runs the TypeScript check without writing files.
- `npm run lint` runs ESLint, mainly for the React hooks rules. Any warning fails it.
- `npm audit` checks the packages, including the build tools, for published advisories.

## Environment

`VITE_API_BASE_URL` is the base URL of the API, with no trailing slash. The lookup page calls `${VITE_API_BASE_URL}/v1/sample?key=...`.

For local work, I copy `.env.example` to `.env.local` and set the value there. Vite reads this variable when it runs or builds, so I set it before I run `npm run build` for a deployed site.

## How the site works

The site is static files. The status page reads `/status.json` from the same site. Locally, `public/status.json` holds a sample pipeline, so the page works without the nightly job. In production, the nightly job publishes the real file next to the site.

The lookup page calls the API. The first request after a quiet period may be slow, and the page says so while it waits.
