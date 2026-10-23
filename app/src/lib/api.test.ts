import { describe, it, expect } from 'vitest'
import contract from '../../../docs/platform/openapi-serving-template.yaml?raw'
import { sampleUrl } from './api'

// The API's routes, as the contract lists them under `paths:` (two spaces, then /name:).
// platform/serving/tests/test_contract.py checks the API serves exactly these, so an address
// that matches one of them reaches a real route.
const contractPaths = [...contract.matchAll(/^ {2}(\/[^:\s]*):\s*$/gm)].map((match) => match[1])

function pathOf(url: string): string {
  return new URL(url).pathname
}

describe('the API contract', () => {
  it('lists the routes the site calls', () => {
    expect(contractPaths).toContain('/sample')
  })
})

describe('sampleUrl', () => {
  it('asks for a route the API serves', () => {
    expect(contractPaths).toContain(pathOf(sampleUrl('https://api.example.com', 'iceberg')))
  })

  it('puts the key in the query, encoded, so it cannot change the address', () => {
    const url = new URL(sampleUrl('https://api.example.com', 'a/b&c=d'))
    expect(url.searchParams.get('key')).toBe('a/b&c=d')
    expect(url.searchParams.size).toBe(1)
  })

  it('accepts a base address that ends in a slash', () => {
    expect(pathOf(sampleUrl('https://api.example.com/', 'x'))).toBe('/sample')
  })
})

describe('the site', () => {
  // The tests above only protect addresses built here, so no page may build one by hand.
  const sources = import.meta.glob(['../**/*.{ts,tsx}', '!../**/*.test.ts', '!./api.ts'], {
    query: '?raw',
    import: 'default',
    eager: true,
  }) as Record<string, string>

  it('builds every API address with the functions in lib/api.ts', () => {
    const handBuilt = Object.entries(sources)
      .filter(([, text]) => text.includes('VITE_API_BASE_URL}'))
      .map(([file]) => file)
    expect(handBuilt).toEqual([])
  })

  it('reads the source files it checks', () => {
    expect(Object.keys(sources)).toContain('../pages/Lookup.tsx')
  })
})
