import { describe, it, expect } from 'vitest'
import { describePipeline } from './pipelineNames'

describe('describePipeline', () => {
  it.each(['platform_skeleton', 'sample_pipeline'])('names %s the nightly system check, with a note', (name) => {
    const known = describePipeline(name)
    expect(known.title).toBe('Nightly system check')
    expect(known.about).toContain('proves the nightly system works')
  })

  it('tidies the code name of a pipeline it does not know, with no note', () => {
    expect(describePipeline('trail_loader')).toEqual({ title: 'Trail loader' })
  })
})
