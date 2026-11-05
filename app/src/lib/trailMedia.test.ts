import { describe, it, expect } from 'vitest'
import { PHASE_A_TRAIL_IDS, photoFor, profileLine, terrainFor, toFeet } from './trailMedia'

describe('terrainFor', () => {
  it('gives the terrain picture and heights of a known trail', () => {
    const count = terrainFor('grca-bright-angel', 255)
    expect(count?.imageUrl).toBe('/trails/grca-bright-angel-terrain.png')
    expect(count?.elevationsM).toHaveLength(255)
  })

  it('gives nothing if the trail has changed, so old art never sits under a new line', () => {
    expect(terrainFor('grca-bright-angel', 254)).toBeUndefined()
  })

  it('gives nothing for an unknown trail', () => {
    expect(terrainFor('no-such-trail', 10)).toBeUndefined()
  })

  it('has real heights for every trail: the canyon is deep', () => {
    for (const [id, count] of [['grca-bright-angel', 255], ['grca-south-kaibab', 210], ['grca-north-kaibab', 467]] as const) {
      const heights = terrainFor(id, count)?.elevationsM ?? []
      expect(Math.max(...heights) - Math.min(...heights)).toBeGreaterThan(900)
    }
  })
})

describe('photoFor', () => {
  it.each(PHASE_A_TRAIL_IDS)('has a credited photo of %s with a text description', (id) => {
    const photo = photoFor(id)
    expect(photo?.url).toBe(`/trails/${id}.jpg`)
    expect(photo?.alt.length).toBeGreaterThan(20)
    expect(photo?.credit).toContain('Photo:')
    expect(photo?.sourceUrl).toMatch(/^https:\/\/commons\.wikimedia\.org\//)
  })

  it('has no photo for an unknown trail', () => {
    expect(photoFor('no-such-trail')).toBeUndefined()
  })
})

describe('profileLine', () => {
  const line = profileLine([2000, 1000, 1500], 300, 100)

  it('runs from the left edge to the right edge', () => {
    expect(line[0].x).toBe(0)
    expect(line[2].x).toBe(300)
  })

  it('puts high ground near the top', () => {
    expect(line[0].y).toBeLessThan(line[2].y)
    expect(line[2].y).toBeLessThan(line[1].y)
  })
})

describe('toFeet', () => {
  it('converts meters to whole feet', () => {
    expect(toFeet(1000)).toBe(3281)
  })
})
