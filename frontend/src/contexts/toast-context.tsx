/**
 * Toast context stub for Phase A
 * This will be replaced with a full implementation in Phase B
 *
 * Phase A stub - Fast Refresh warnings are acceptable until full implementation in Phase B
 * The file exports both context and components, which triggers Fast Refresh warnings.
 * This is intentional for the stub and will be restructured in Phase B.
 */

/* eslint-disable react-refresh/only-export-components */

import { createContext, useContext, type ReactNode } from 'react'

export interface ToastContextValue {
  showToast: (message: string, error?: unknown) => void
}

export const ToastContext = createContext<ToastContextValue | null>(null)

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within ToastProvider')
  }
  return context
}

interface ToastProviderProps {
  children: ReactNode
}

/**
 * Stub ToastProvider for Phase A
 * Logs messages to console instead of showing UI toasts
 */
export function ToastProvider({ children }: ToastProviderProps) {
  const showToast = (message: string, error?: unknown) => {
    // In Phase A, just log to console
    console.log('[Toast]', message)
    if (error) {
      console.error('[Toast Error]', error)
    }
  }

  return <ToastContext.Provider value={{ showToast }}>{children}</ToastContext.Provider>
}
