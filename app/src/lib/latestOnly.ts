/**
 * Answers can arrive out of order, so a slow answer about an older choice must not replace the
 * newest one. Call the returned function when a request starts; it gives back a check to run when
 * the answer arrives.
 */
export function latestOnly() {
  let newest = 0
  return () => {
    newest += 1
    const mine = newest
    return () => mine === newest
  }
}
