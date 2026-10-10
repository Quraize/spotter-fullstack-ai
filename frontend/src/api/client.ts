import type { Plan, PlanRequest } from './types'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fields?: Record<string, string[]>

  constructor(status: number, code: string, message: string, fields?: Record<string, string[]>) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.fields = fields
  }
}

interface ErrorBody {
  error?: { code?: string; message?: string; fields?: Record<string, string[]> }
}

export async function postPlan(request: PlanRequest, signal?: AbortSignal): Promise<Plan> {
  let response: Response
  try {
    response = await fetch('/api/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'network', 'Could not reach the server. Check your connection and try again.')
  }

  const text = await response.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = null
  }

  if (!response.ok) {
    const error = (body as ErrorBody | null)?.error
    if (error?.code && error.message) {
      throw new ApiError(response.status, error.code, error.message, error.fields)
    }
    throw new ApiError(response.status, 'http_error', `The server returned HTTP ${response.status}.`)
  }
  return body as Plan
}

// Form labels, so a 400 reads "Load weight: ..." rather than "load_weight_lb: ...".
const FIELD_LABELS: Record<string, string> = {
  origin: 'Origin',
  destination: 'Destination',
  departure_time: 'Departure date & time',
  load_weight_lb: 'Load weight',
  sample_interval_miles: 'Sample interval',
}

/** The text to show a driver for an API error: field messages when there are any, else the server's message. */
export function apiErrorMessage(error: ApiError): string {
  const entries = Object.entries(error.fields ?? {})
  if (entries.length === 0) return error.message
  return entries.map(([field, messages]) => `${FIELD_LABELS[field] ?? field}: ${messages.join(' ')}`).join(' ')
}
