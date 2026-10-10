# Portfolio Data Platform site

The public website for the data platform. It has a home page with the five project cards, a status page, and a lookup page. It is a Vite, React, and TypeScript app that builds to plain static files, so the site has no server of its own. Only the lookup page talks to the API.

## Run it

Run these commands from this `app` folder:

- `npm install` installs the pinned versions.
- `npm run dev` starts the dev server at http://localhost:5173.
- `npm run build` checks types, then writes static files to `dist`.
- `npm run preview` serves the built `dist` folder locally.
- `npm test` runs the unit tests with Vitest.
- `npm run typecheck` runs the TypeScript check without writing files.

## Environment

`VITE_API_BASE_URL` is the base URL of the API, with no trailing slash. The lookup page calls `${VITE_API_BASE_URL}/v1/sample?key=...`.

For local work, copy `.env.example` to `.env.local` and set the value there. Vite reads this variable when it runs or builds, so set it before you run `npm run build` for a deployed site.

## How the site works

The site is static files. The status page reads `/status.json` from the same site. Locally, `public/status.json` holds a sample pipeline so the page works without the nightly job. In production, the job publishes the real file next to the site.

The lookup page calls the API. The first request after a quiet period may be slow, and the page says so while it waits.
