/**
 * AuthGate component.
 * Suspends rendering of children until authentication state resolves.
 * Shows loading spinner during auth check, error screen with retry for failures.
 */

import { type ReactNode } from 'react'
import { useAuthContext } from '@/contexts/auth-context'
import { Button } from '@/components/ui/button'

interface AuthGateProps {
  children: ReactNode
}

/**
 * Blank screen shown while checking authentication.
 * No animation to avoid visual noise during testing.
 */
function AuthLoading() {
  return (
    <div
      className="h-screen w-full bg-zinc-950"
      data-testid="auth.gate.loading"
    />
  )
}

/**
 * Error screen shown when auth check fails (non-401 errors).
 */
function AuthError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  return (
    <div
      className="flex h-screen w-full items-center justify-center bg-zinc-950"
      data-testid="auth.gate.error"
    >
      <div className="flex max-w-md flex-col items-center gap-4 rounded-lg border border-zinc-800 bg-zinc-900 p-8 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-900/50">
          <svg
            className="h-6 w-6 text-red-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
        </div>
        <h2 className="text-lg font-semibold text-zinc-50">Authentication Error</h2>
        <p className="text-sm text-zinc-400">
          Unable to verify your authentication status. Please try again.
        </p>
        <p className="text-xs text-zinc-500">{error.message}</p>
        <Button
          variant="primary"
          onClick={onRetry}
          data-testid="auth.gate.error.retry"
        >
          Retry
        </Button>
      </div>
    </div>
  )
}

/**
 * AuthGate component.
 * Blocks rendering of children until auth state is resolved.
 *
 * States:
 * - Loading: Shows spinner while checking auth
 * - Error (non-401): Shows error screen with retry button
 * - Unauthenticated (401): AuthProvider handles redirect, gate shows nothing
 * - Authenticated: Renders children
 */
export function AuthGate({ children }: AuthGateProps) {
  const { isLoading, isAuthenticated, error, refetch } = useAuthContext()

  // Show loading state while auth check is in progress
  if (isLoading) {
    return <AuthLoading />
  }

  // Show error screen for non-401 errors (server errors, network issues)
  if (error) {
    return <AuthError error={error} onRetry={refetch} />
  }

  // If not authenticated and no error, redirect is in progress (handled by AuthProvider)
  // Don't render children to prevent flash of content
  if (!isAuthenticated) {
    return <AuthLoading />
  }

  // User is authenticated - render the app
  return <>{children}</>
}
