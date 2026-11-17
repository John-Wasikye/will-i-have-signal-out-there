import { useEffect, useState } from 'react'

const MINUTE_MS = 60_000

/** The current time, checked again every minute, so lateness and time left do not go stale. */
export function useNow(): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), MINUTE_MS)
    return () => clearInterval(timer)
  }, [])
  return now
}
