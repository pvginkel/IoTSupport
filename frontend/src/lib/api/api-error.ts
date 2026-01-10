/**
 * Simplified API error handling for Phase A.
 * This will be expanded in Phase B when we have generated types.
 */

/**
 * Wrap API error payloads in a proper Error subclass so unhandled rejections
 * surface meaningful messages and preserve structured details.
 */
export class ApiError extends Error {
  status?: number
  details?: unknown
  raw: unknown
  cause?: unknown

  constructor(raw: unknown) {
    super(parseApiError(raw))
    this.name = 'ApiError'
    this.raw = raw

    if (typeof raw === 'object' && raw !== null) {
      const maybeObject = raw as Record<string, unknown>

      if (typeof maybeObject.status === 'number') {
        this.status = maybeObject.status
      }

      if ('details' in maybeObject) {
        this.details = maybeObject.details
      }
    }

    // Preserve the original payload for debugging
    this.cause = raw

    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, ApiError)
    }
  }
}

export function toApiError(error: unknown): Error {
  return error instanceof Error ? error : new ApiError(error)
}

/**
 * Parse API error into a user-friendly message
 */
function parseApiError(error: unknown): string {
  // Handle fetch/network errors
  if (error instanceof Error) {
    if ('status' in error && typeof (error as Error & { status: unknown }).status === 'number') {
      const fetchError = error as Error & { status: number }
      if (fetchError.status === 404) {
        return 'Resource not found'
      }
      if (fetchError.status >= 500) {
        return 'Server error occurred. Please try again later.'
      }
    }
    return error.message || 'An unexpected error occurred'
  }

  // Handle structured API error responses with 'error' field
  if (typeof error === 'object' && error !== null && 'error' in error) {
    const apiError = error as { error: unknown }
    if (typeof apiError.error === 'string') {
      return apiError.error
    }
  }

  // Handle error objects with message property
  if (typeof error === 'object' && error !== null && 'message' in error) {
    return String((error as { message: unknown }).message)
  }

  // Handle string errors
  if (typeof error === 'string') {
    return error
  }

  // Fallback for unknown error formats
  return 'An unexpected error occurred'
}
