export function DevelopmentBanner() {
  return (
    <div className="dev-banner" role="status">
      <p>
        <strong>Under development:</strong> this site does not show real coverage or satellite times
        yet. The data pipeline, the automated job that will collect and check the data, is still being
        built.
      </p>
    </div>
  )
}
