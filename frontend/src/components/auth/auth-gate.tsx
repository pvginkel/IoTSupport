/**
 * AuthGate component.
 * Suspends rendering of children until authentication state resolves.
 * Shows loading spinner during auth check, error screen with retry for failures.
 */

import { type ReactNode } from 'react';
import { useAuthContext } from '@/contexts/auth-context';
import { Button } from '@/components/primitives/button';
import { ApiError } from '@/lib/api/api-error';

interface AuthGateProps {
  children: ReactNode;
}

/**
 * Blank screen shown while checking authentication.
 * No animation to avoid visual noise during testing.
 */
function AuthLoading() {
  return (
    <div
      className="h-screen w-full bg-background"
      data-testid="auth.gate.loading"
    />
  );
}

/**
 * Derive user-friendly error title and description based on error type.
 * Server errors (5xx, network) get server-focused messaging,
 * not auth-focused since 401s are already handled by redirect.
 */
function getErrorDisplay(error: Error): { title: string; description: string } {
  const status = error instanceof ApiError ? error.status : undefined;

  // Network errors (no status) - connection failed entirely
  if (status === undefined) {
    return {
      title: 'Connection Error',
      description: 'Unable to connect to the server. Please check your network connection.',
    };
  }

  // 502 Bad Gateway - backend service is down
  if (status === 502) {
    return {
      title: 'Server Unavailable',
      description: 'The server is currently unavailable. Please try again shortly.',
    };
  }

  // 503 Service Unavailable
  if (status === 503) {
    return {
      title: 'Service Unavailable',
      description: 'The service is temporarily unavailable. Please try again shortly.',
    };
  }

  // 504 Gateway Timeout
  if (status === 504) {
    return {
      title: 'Server Timeout',
      description: 'The server took too long to respond. Please try again.',
    };
  }

  // Other 5xx errors
  if (status >= 500) {
    return {
      title: 'Server Error',
      description: 'The server encountered an error. Please try again later.',
    };
  }

  // Fallback for unexpected error types
  return {
    title: 'Connection Error',
    description: 'An unexpected error occurred. Please try again.',
  };
}

/**
 * Error screen shown when auth check fails (non-401 errors).
 * Displays server-focused messaging since 401s redirect to login.
 */
function AuthError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const { title, description } = getErrorDisplay(error);

  return (
    <div
      className="flex h-screen w-full items-center justify-center bg-background"
      data-testid="auth.gate.error"
    >
      <div className="flex max-w-md flex-col items-center gap-4 rounded-lg border border-border bg-card p-8 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/20">
          <svg
            className="h-6 w-6 text-destructive"
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
        <h2 className="text-lg font-semibold text-foreground">{title}</h2>
        <p className="text-sm text-muted-foreground">{description}</p>
        <Button
          variant="primary"
          onClick={onRetry}
          data-testid="auth.gate.error.retry"
        >
          Retry
        </Button>
      </div>
    </div>
  );
}

/**
 * AuthGate component.
 * Blocks rendering of children until auth state is resolved.
 *
 * States:
 * - Loading: Shows blank screen while checking auth
 * - Error (non-401): Shows error screen with retry button
 * - Unauthenticated (401): Middleware handles redirect, gate shows blank
 * - Authenticated: Renders children
 */
export function AuthGate({ children }: AuthGateProps) {
  const { isLoading, isAuthenticated, error, refetch } = useAuthContext();

  // Show loading state while auth check is in progress
  if (isLoading) {
    return <AuthLoading />;
  }

  // Show error screen for non-401 errors (server errors, network issues)
  if (error) {
    return <AuthError error={error} onRetry={refetch} />;
  }

  // If not authenticated and no error, redirect is in progress (handled by middleware)
  // Don't render children to prevent flash of content
  if (!isAuthenticated) {
    return <AuthLoading />;
  }

  // User is authenticated - render the app
  return <>{children}</>;
}
