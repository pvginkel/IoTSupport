import { QueryClient } from '@tanstack/react-query'

// Store the toast function reference to avoid circular dependencies
// This will be set up in Phase B when we implement the toast system
let toastFunction: ((message: string, error?: unknown) => void) | null = null

export function setToastFunction(handler: (message: string, error?: unknown) => void) {
  toastFunction = handler
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        // Don't retry on 404s
        if (error instanceof Error && 'status' in error) {
          const status = (error as Error & { status: number }).status
          if (status === 404) {
            return false
          }
          // Don't retry on client errors (4xx)
          if (status >= 400 && status < 500) {
            return false
          }
        }

        // Retry up to 3 times for server errors and network issues
        return failureCount < 3
      },
      retryDelay: attemptIndex => Math.min(1000 * 2 ** attemptIndex, 30000),
      staleTime: 5 * 60 * 1000, // 5 minutes
    },
    mutations: {
      retry: false, // Don't retry mutations by default
      onError: (error: unknown) => {
        const message =
          error instanceof Error ? error.message : 'An unexpected error occurred'

        // Show mutation errors to the user when toast system is available
        if (toastFunction) {
          toastFunction(message, error)
        } else {
          // Phase A fallback: log mutation errors to console so they aren't silently swallowed
          console.error('[Mutation Error]', message, error)
        }
      },
    },
  },
})
