import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useFrameThrottledValue } from './useFrameThrottledValue'

let frames: FrameRequestCallback[]

beforeEach(() => {
  frames = []
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
    frames.push(cb)
    return frames.length
  })
  vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

function flushFrame() {
  const pending = frames
  frames = []
  act(() => {
    for (const cb of pending) cb(performance.now())
  })
}

describe('useFrameThrottledValue', () => {
  it('returns the initial value immediately', () => {
    const { result } = renderHook(({ v }) => useFrameThrottledValue(v), { initialProps: { v: 0 } })
    expect(result.current).toBe(0)
    expect(frames).toHaveLength(0)
  })

  it('commits a burst of changes once, with the latest value, on the next frame', () => {
    const { result, rerender } = renderHook(({ v }) => useFrameThrottledValue(v), { initialProps: { v: 0 } })
    rerender({ v: 1 })
    rerender({ v: 2 })
    rerender({ v: 3 })
    expect(result.current).toBe(0)
    expect(frames).toHaveLength(1)

    flushFrame()
    expect(result.current).toBe(3)
  })

  it('schedules a new frame for changes made after a commit', () => {
    const { result, rerender } = renderHook(({ v }) => useFrameThrottledValue(v), { initialProps: { v: 0 } })
    rerender({ v: 1 })
    flushFrame()
    expect(result.current).toBe(1)

    rerender({ v: 2 })
    expect(result.current).toBe(1)
    expect(frames).toHaveLength(1)
    flushFrame()
    expect(result.current).toBe(2)
  })

  it('cancels a pending frame on unmount', () => {
    const { rerender, unmount } = renderHook(({ v }) => useFrameThrottledValue(v), { initialProps: { v: 0 } })
    rerender({ v: 1 })
    unmount()
    expect(window.cancelAnimationFrame).toHaveBeenCalledTimes(1)
  })
})
