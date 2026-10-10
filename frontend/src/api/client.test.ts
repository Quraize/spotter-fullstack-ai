import { afterEach, describe, expect, it, vi } from 'vitest'

import { planFixture } from '../test/fixtures/plan'
import { ApiError, apiErrorMessage, postPlan } from './client'
import type { PlanRequest } from './types'

const request: PlanRequest = {
  origin: 'Chicago, IL',
  destination: 'Denver, CO',
  departure_time: '2026-10-11T08:00:00-05:00',
  load_weight_lb: 42000,
  sample_interval_miles: 25,
}

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('postPlan', () => {
  it('posts the request as JSON and returns the plan', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, planFixture))
    vi.stubGlobal('fetch', fetchMock)

    const plan = await postPlan(request)

    expect(plan.recommended_route_id).toBe('r2')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/plan')
    expect(init.method).toBe('POST')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body)).toEqual(request)
  })

  it('turns a structured error response into an ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(422, { error: { code: 'geocode_not_found', message: "No location found for 'Atlantis'" } }),
      ),
    )
    const err = await postPlan(request).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(422)
    expect(err.code).toBe('geocode_not_found')
    expect(err.message).toBe("No location found for 'Atlantis'")
  })

  it('keeps per-field validation messages', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(400, {
          error: { code: 'validation_error', message: 'Invalid request.', fields: { departure_time: ['Include a UTC offset.'] } },
        }),
      ),
    )
    const err = (await postPlan(request).catch((e) => e)) as ApiError
    expect(err.code).toBe('validation_error')
    expect(err.fields?.departure_time).toEqual(['Include a UTC offset.'])
  })

  it('handles non-JSON failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>Bad gateway</html>', { status: 502 })))
    const err = (await postPlan(request).catch((e) => e)) as ApiError
    expect(err.code).toBe('http_error')
    expect(err.status).toBe(502)
    expect(err.message).toMatch(/502/)
  })

  it('reports network failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const err = (await postPlan(request).catch((e) => e)) as ApiError
    expect(err.code).toBe('network')
    expect(err.status).toBe(0)
  })
})

describe('apiErrorMessage', () => {
  it('uses the server message when there are no field errors', () => {
    expect(apiErrorMessage(new ApiError(503, 'provider_unavailable', 'Weather service is down.'))).toBe(
      'Weather service is down.',
    )
  })

  it('lists field errors with human labels instead of the generic message', () => {
    const error = new ApiError(400, 'validation_error', 'Invalid request.', {
      origin: ['This field may not be blank.'],
      sample_interval_miles: ['"15" is not a valid choice.'],
    })
    expect(apiErrorMessage(error)).toBe(
      'Origin: This field may not be blank. Sample interval: "15" is not a valid choice.',
    )
  })

  it('falls back to the raw field name for unknown fields', () => {
    const error = new ApiError(400, 'validation_error', 'Invalid request.', { non_field_errors: ['Nope.'] })
    expect(apiErrorMessage(error)).toBe('non_field_errors: Nope.')
  })
})
