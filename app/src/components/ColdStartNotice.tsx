export function ColdStartNotice() {
  return (
    <div className="notice" role="status">
      <p>
        The first request after a period of inactivity may take up to 10 seconds while the service initializes.
      </p>
    </div>
  )
}
