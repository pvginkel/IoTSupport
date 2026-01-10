import { useState } from 'react'
import { createRootRoute, Outlet } from '@tanstack/react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { Sidebar } from '@/components/layout/sidebar'
import { ToastProvider } from '@/contexts/toast-context'
import { queryClient } from '@/lib/query-client'

export const Route = createRootRoute({
  component: RootLayout,
})

function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AppShellFrame />
      </ToastProvider>
    </QueryClientProvider>
  )
}

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

  return (
    <div
      className="flex h-screen flex-col overflow-hidden"
      data-testid="app-shell.root"
      data-mobile-menu-state={mobileMenuOpen ? 'open' : 'closed'}
    >
      <div className="flex flex-1 overflow-hidden" data-testid="app-shell.layout">
        <div className="hidden lg:block" data-testid="app-shell.sidebar.desktop">
          <Sidebar
            isCollapsed={sidebarCollapsed}
            onToggle={toggleSidebar}
            onNavigate={handleNavigation}
            variant="desktop"
          />
        </div>

        {mobileMenuOpen && (
          <div className="fixed inset-0 z-[100] lg:hidden" data-testid="app-shell.mobile-overlay">
            <div
              className="absolute inset-0 bg-black/50"
              data-testid="app-shell.mobile-overlay.dismiss"
              onClick={() => setMobileMenuOpen(false)}
            />
            <div
              className="absolute left-0 top-0 h-full"
              id="app-shell-mobile-menu"
              data-testid="app-shell.sidebar.mobile"
            >
              <Sidebar onNavigate={handleNavigation} variant="mobile" />
            </div>
          </div>
        )}

        <div className="flex flex-1 flex-col overflow-hidden">
          <div
            className="border-b border-zinc-800 bg-zinc-950 lg:hidden"
            data-testid="app-shell.mobile-toggle"
          >
            <button
              type="button"
              onClick={toggleMobileMenu}
              className="flex w-full cursor-pointer items-center justify-between p-4 hover:bg-zinc-900"
              aria-expanded={mobileMenuOpen}
              aria-controls="app-shell-mobile-menu"
              aria-label="Toggle navigation menu"
              data-testid="app-shell.mobile-toggle.button"
            >
              <span className="text-sm font-medium text-zinc-50">Menu</span>
              <span aria-hidden className="text-xl">
                ☰
              </span>
            </button>
          </div>

          <main className="flex-1 overflow-auto" data-testid="app-shell.content">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  )
}
