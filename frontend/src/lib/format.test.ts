import { describe, expect, it } from 'vitest'

import {
  defaultDepartureLocal,
  formatDateTime,
  formatDuration,
  formatLoad,
  formatMiles,
  formatRisk,
  formatTime,
  toIsoWithOffset,
} from './format'

describe('formatDuration', () => {
  it('renders hours and zero-padded minutes', () => {
    expect(formatDuration(50040)).toBe('13h 54m')
    expect(formatDuration(0)).toBe('0h 00m')
    expect(formatDuration(3599)).toBe('1h 00m')
    expect(formatDuration(90)).toBe('0h 02m')
  })
})

describe('formatMiles', () => {
  it('rounds and groups thousands', () => {
    expect(formatMiles(1008.4)).toBe('1,008 mi')
    expect(formatMiles(96.25, 1)).toBe('96.3 mi')
    expect(formatMiles(0)).toBe('0 mi')
  })
})

describe('formatLoad and formatRisk', () => {
  it('formats pounds and the 0-4 risk scale', () => {
    expect(formatLoad(42000)).toBe('42,000 lb')
    expect(formatRisk(0.099)).toBe('0.10')
    expect(formatRisk(0)).toBe('0.00')
  })
})

describe('toIsoWithOffset', () => {
  it('turns a datetime-local value into ISO 8601 with the browser offset for the same instant', () => {
    const iso = toIsoWithOffset('2026-10-11T08:00')
    expect(iso.startsWith('2026-10-11T08:00:00')).toBe(true)
    expect(iso).toMatch(/[+-]\d\d:\d\d$/)
    expect(new Date(iso).getTime()).toBe(new Date(2026, 9, 11, 8, 0).getTime())
  })

  it('throws on an unparsable value', () => {
    expect(() => toIsoWithOffset('')).toThrow()
    expect(() => toIsoWithOffset('not a date')).toThrow()
  })
})

describe('defaultDepartureLocal', () => {
  it('is the next full hour as a datetime-local value', () => {
    expect(defaultDepartureLocal(new Date(2026, 9, 11, 8, 15))).toBe('2026-10-11T09:00')
    expect(defaultDepartureLocal(new Date(2026, 9, 11, 8, 0))).toBe('2026-10-11T09:00')
    expect(defaultDepartureLocal(new Date(2026, 9, 11, 23, 30))).toBe('2026-10-12T00:00')
  })
})

describe('formatDateTime and formatTime', () => {
  it('render a readable local date-time and time', () => {
    expect(formatDateTime('2026-10-11T08:05:00-05:00')).toMatch(/^[A-Z][a-z]{2}, [A-Z][a-z]{2} \d{1,2}, \d{2}:\d{2}$/)
    expect(formatTime('2026-10-11T08:05:00-05:00')).toMatch(/^\d{2}:\d{2}$/)
  })

  it('never renders midnight as 24:00', () => {
    const midnightLocal = new Date(2026, 9, 11, 0, 0).toISOString()
    expect(formatTime(midnightLocal)).toBe('00:00')
  })
})
