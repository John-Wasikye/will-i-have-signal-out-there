import { formatUtc } from '../lib/status'

interface LateNoticeProps {
  lastGoodRunUtc: string | null
  pipelineName?: string
}

export function LateNotice({ lastGoodRunUtc, pipelineName }: LateNoticeProps) {
  const subject = pipelineName ? `${pipelineName} is late or has failed.` : 'A pipeline is late or has failed.'
  const lastRun = lastGoodRunUtc
    ? `The last good run was ${formatUtc(lastGoodRunUtc)}.`
    : 'No good run has finished yet.'

  return (
    <div className="notice notice-late" role="status">
      <p>
        {subject} {lastRun}
      </p>
    </div>
  )
}
