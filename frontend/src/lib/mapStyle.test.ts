import { describe, expect, it } from 'vitest'

import { BASEMAP_LAND, MAP_STYLE, OTHER_ROUTE_COLOR, SELECTED_ROUTE_COLOR } from './mapStyle'

/** WCAG relative luminance of a #rrggbb colour. */
function luminance(hex: string): number {
  const channel = (i: number) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5)
}

/** WCAG contrast ratio, 1 (identical) to 21 (black on white). */
function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

describe('basemap', () => {
  it('is a keyless OpenFreeMap style served over https', () => {
    expect(MAP_STYLE).toMatch(/^https:\/\/tiles\.openfreemap\.org\/styles\/[a-z]+$/)
  })

  it('is the coloured "liberty" style, not the grey "positron" one', () => {
    expect(MAP_STYLE.endsWith('/liberty')).toBe(true)
  })
})

describe('route colours on the basemap land colour', () => {
  it('are #rrggbb so the contrast check below is meaningful', () => {
    for (const c of [BASEMAP_LAND, SELECTED_ROUTE_COLOR, OTHER_ROUTE_COLOR]) expect(c).toMatch(/^#[0-9a-f]{6}$/)
  })

  it('selected route stands out (WCAG 4.5:1, the text threshold)', () => {
    expect(contrast(SELECTED_ROUTE_COLOR, BASEMAP_LAND)).toBeGreaterThanOrEqual(4.5)
  })

  it('other routes stay readable (WCAG 3:1, the non-text threshold) but quieter than the selected one', () => {
    const other = contrast(OTHER_ROUTE_COLOR, BASEMAP_LAND)
    expect(other).toBeGreaterThanOrEqual(3)
    expect(other).toBeLessThan(contrast(SELECTED_ROUTE_COLOR, BASEMAP_LAND))
  })

  it('selected and other routes are different colours', () => {
    expect(SELECTED_ROUTE_COLOR).not.toBe(OTHER_ROUTE_COLOR)
  })
})
