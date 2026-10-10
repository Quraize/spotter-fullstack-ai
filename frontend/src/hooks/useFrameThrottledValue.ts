import { useEffect, useRef, useState } from 'react'

/**
 * Returns `value`, but updates at most once per animation frame with the
 * latest value seen. A range input fires many change events per frame while
 * dragging; the slider label can follow every event while the map only
 * re-styles once per painted frame.
 */
export function useFrameThrottledValue<T>(value: T): T {
  const [committed, setCommitted] = useState(value)
  const latest = useRef(value)
  const frame = useRef<number | null>(null)

  useEffect(() => {
    latest.current = value
    if (Object.is(committed, value) || frame.current !== null) return
    frame.current = requestAnimationFrame(() => {
      frame.current = null
      setCommitted(latest.current)
    })
  }, [value, committed])

  useEffect(
    () => () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current)
    },
    [],
  )

  return committed
}
