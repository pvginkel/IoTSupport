/**
 * Root layout component.
 * Integrates authentication, top bar, and sidebar navigation.
 */

import { useState } from 'react'
import { createRootRoute, Outlet } from '@tanstack/react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { Sidebar } from '@/components/layout/sidebar'
import { TopBar } from '@/components/layout/top-bar'
import { ToastProvider } from '@/contexts/toast-context'
import { AuthProvider } from '@/contexts/auth-context'
import { SseProvider } from '@/contexts/sse-context'
import { AuthGate } from '@/components/auth/auth-gate'
import { queryClient } from '@/lib/query-client'

export const Route = createRootRoute({
  component: RootLayout,
})

/**
 * Root layout wrapper.
 * Sets up providers in correct order:
 * 1. QueryClientProvider - enables data fetching
 * 2. ToastProvider - enables toast notifications
 * 3. AuthProvider - provides auth state and handles 401 redirects
 * 4. AuthGate - blocks rendering until authenticated
 * 5. SseProvider - opens SSE connection (only when authenticated)
 */
function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthProvider>
          <AuthGate>
            <SseProvider>
              <AppShellFrame />
            </SseProvider>
          </AuthGate>
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  )
}

/**
 * App shell with top bar, sidebar, and main content area.
 * Handles responsive layout with mobile overlay menu.
 */
function AppShellFrame() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const toggleSidebar = () => {
    setSidebarCollapsed(prev => !prev)
  }

  const toggleMobileMenu = () => {
    setMobileMenuOpen(prev => !prev)
  }

  const handleNavigation = () => {
    setMobileMenuOpen(false)
  }

  // Determine which toggle to use based on viewport
  // On mobile (< lg), toggle the mobile menu overlay
  // On desktop (>= lg), toggle the sidebar collapse state
  const handleMenuToggle = () => {
    // Check if we're on mobile viewport
    const isMobile = window.innerWidth < 1024 // lg breakpoint
    if (isMobile) {
      toggleMobileMenu()
    } else {
      toggleSidebar()
    }
  }

  return (
    <div
      className="flex h-screen flex-col overflow-hidden bg-background"
      data-testid="app-shell.root"
      data-mobile-menu-state={mobileMenuOpen ? 'open' : 'closed'}
    >
      {/* Top bar - single instance, always visible */}
      <TopBar onMenuToggle={handleMenuToggle} />

      {/* Content area with sidebar */}
      <div className="flex flex-1 overflow-hidden" data-testid="app-shell.layout">
        {/* Desktop sidebar */}
        <div className="hidden lg:block" data-testid="app-shell.sidebar.desktop">
          <Sidebar
            isCollapsed={sidebarCollapsed}
            onNavigate={handleNavigation}
            variant="desktop"
          />
        </div>

        {/* Mobile overlay menu */}
        {mobileMenuOpen && (
          <div className="fixed inset-0 z-[100] lg:hidden" data-testid="app-shell.mobile-overlay">
            {/* Backdrop - clicking dismisses menu */}
            <div
              className="absolute inset-0 bg-black/50"
              data-testid="app-shell.mobile-overlay.dismiss"
              onClick={() => setMobileMenuOpen(false)}
            />
            {/* Mobile sidebar container */}
            <div
              className="absolute left-0 top-0 h-full"
              id="app-shell-mobile-menu"
              data-testid="app-shell.sidebar.mobile"
            >
              <Sidebar onNavigate={handleNavigation} variant="mobile" />
            </div>
          </div>
        )}

        {/* Main content */}
        <main className="flex-1 overflow-auto" data-testid="app-shell.content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
