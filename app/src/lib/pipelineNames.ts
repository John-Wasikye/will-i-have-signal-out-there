export interface PipelineDescription {
  title: string
  about?: string
}

const SYSTEM_CHECK: PipelineDescription = {
  title: 'Nightly system check',
  about:
    'A small test job that proves the nightly system works from start to finish. It does not make the trail predictions: those are covered at the top of this page.',
}

const KNOWN_PIPELINES: Record<string, PipelineDescription> = {
  platform_skeleton: SYSTEM_CHECK,
  sample_pipeline: SYSTEM_CHECK,
}

function plainName(codeName: string): string {
  const words = codeName.replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** One name for a pipeline, shared by its card and its late notice, so they never disagree. */
export function describePipeline(codeName: string): PipelineDescription {
  return KNOWN_PIPELINES[codeName] ?? { title: plainName(codeName) }
}
