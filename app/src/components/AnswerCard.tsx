import { formatUtc } from '../lib/status'

export interface SampleRow {
  key: string
  value: string | number | null
  last_good_run_utc: string | null
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
        <dd>{row.value === null ? 'No value' : String(row.value)}</dd>
        <dt>Last good run</dt>
        <dd>{formatUtc(row.last_good_run_utc)}</dd>
        <dt>Late</dt>
        <dd>{row.late ? 'Yes' : 'No'}</dd>
      </dl>
    </section>
  )
}
