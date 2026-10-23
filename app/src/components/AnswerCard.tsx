import { formatUtc } from '../lib/status'

/** One answer from GET /sample (SampleAnswer in docs/platform/openapi-serving-template.yaml). */
export interface SampleRow {
  key: string
  value: string
  last_good_run_utc: string
  late: boolean
}

interface AnswerCardProps {
  row: SampleRow
}

export function AnswerCard({ row }: AnswerCardProps) {
  return (
    <section className="card" aria-labelledby="answer-heading">
      <h2 id="answer-heading">Result</h2>
      <dl className="facts">
        <dt>Key</dt>
        <dd>{row.key}</dd>
        <dt>Value</dt>
        <dd>{row.value}</dd>
        <dt>Last good run</dt>
        <dd>{formatUtc(row.last_good_run_utc)}</dd>
        <dt>Late</dt>
        <dd>{row.late ? 'Yes' : 'No'}</dd>
      </dl>
    </section>
  )
}
