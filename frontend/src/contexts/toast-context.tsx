/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { ulid } from 'ulid'
import { ToastContainer, type Toast, type ToastType, type ToastOptions } from '@/components/ui/toast'

export interface ToastContextValue {
  showToast: (type: ToastType, message: string, options?: ToastOptions) => void
  showSuccess: (message: string, options?: ToastOptions) => void
  showError: (message: string, options?: ToastOptions) => void
  showWarning: (message: string, options?: ToastOptions) => void
  showInfo: (message: string, options?: ToastOptions) => void
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

export function ToastProvider({ children }: ToastProviderProps) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const showToast = useCallback((type: ToastType, message: string, options?: ToastOptions) => {
    const id = ulid()
    const toast: Toast = {
      id,
      type,
      message,
      duration: options?.duration,
      action: options?.action
    }
    setToasts(prev => [...prev, toast])
  }, [])

  const showSuccess = useCallback((message: string, options?: ToastOptions) => {
    showToast('success', message, options)
  }, [showToast])

  const showError = useCallback((message: string, options?: ToastOptions) => {
    showToast('error', message, options)
  }, [showToast])

  const showWarning = useCallback((message: string, options?: ToastOptions) => {
    showToast('warning', message, options)
  }, [showToast])

  const showInfo = useCallback((message: string, options?: ToastOptions) => {
    showToast('info', message, options)
  }, [showToast])

  return (
    <ToastContext.Provider value={{ showToast, showSuccess, showError, showWarning, showInfo }}>
      {children}
      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </ToastContext.Provider>
  )
}
