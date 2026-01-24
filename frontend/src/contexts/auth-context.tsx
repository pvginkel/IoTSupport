/* eslint-disable react-refresh/only-export-components */
/**
 * Authentication context and provider.
 * Provides auth state to the component tree and handles 401 redirects.
 */

import { createContext, useContext, useEffect, type ReactNode } from 'react'
import { useAuth, type UserInfo } from '@/hooks/use-auth'
import { buildLoginUrl } from '@/lib/auth-redirect'
import { isTestMode } from '@/lib/config/test-mode'
import { emitTestEvent } from '@/lib/test/event-emitter'
import { TestEventKind, type UiStateTestEvent } from '@/types/test-events'

/**
 * Auth context value shape.
 */
export interface AuthContextValue {
  user: UserInfo | null
  isLoading: boolean
  isAuthenticated: boolean
  error: Error | null
  logout: () => void
  refetch: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

/**
 * Hook to access auth context.
 * Must be used within AuthProvider.
 */
export function useAuthContext(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuthContext must be used within AuthProvider')
  }
  return context
}

interface AuthProviderProps {
  children: ReactNode
}

/**
 * Perform logout by navigating to the logout endpoint.
 */
function performLogout(): void {
  window.location.href = '/api/auth/logout'
}

/**
 * AuthProvider component.
 * Fetches auth state on mount and handles 401 redirects.
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const { user, isLoading, isAuthenticated, isUnauthenticated, error, refetch } = useAuth()

  // Emit auth state events for test instrumentation
  useEffect(() => {
    if (!isTestMode()) return

    if (isLoading) {
      const loadingPayload: Omit<UiStateTestEvent, 'timestamp'> = {
        kind: TestEventKind.UI_STATE,
        scope: 'auth',
        phase: 'loading',
      }
      emitTestEvent(loadingPayload)
    } else if (isAuthenticated && user) {
      const readyPayload: Omit<UiStateTestEvent, 'timestamp'> = {
        kind: TestEventKind.UI_STATE,
        scope: 'auth',
        phase: 'ready',
        metadata: { userId: user.subject },
      }
      emitTestEvent(readyPayload)
    } else if (error) {
      const errorPayload: Omit<UiStateTestEvent, 'timestamp'> = {
        kind: TestEventKind.UI_STATE,
        scope: 'auth',
        phase: 'error',
        metadata: { message: error.message },
      }
      emitTestEvent(errorPayload)
    }
  }, [isLoading, isAuthenticated, user, error])

  // Handle 401 redirect - when unauthenticated, redirect to login
  useEffect(() => {
    if (isUnauthenticated) {
      const loginUrl = buildLoginUrl()

      // Emit redirecting event for test instrumentation before redirect
      // Using 'submit' phase as proxy for 'redirecting' since it's in the allowed phases
      if (isTestMode()) {
        const redirectPayload: Omit<UiStateTestEvent, 'timestamp'> = {
          kind: TestEventKind.UI_STATE,
          scope: 'auth',
          phase: 'submit',
          metadata: { targetUrl: loginUrl, action: 'redirecting' },
        }
        emitTestEvent(redirectPayload)
      }

      // Perform the redirect
      window.location.href = loginUrl
    }
  }, [isUnauthenticated])

  const contextValue: AuthContextValue = {
    user,
    isLoading,
    isAuthenticated,
    error,
    logout: performLogout,
    refetch,
  }

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  )
}
