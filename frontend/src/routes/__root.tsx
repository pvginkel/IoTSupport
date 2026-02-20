/**
 * Root layout component.
 * Composes provider groups and renders the app shell.
 */

import { useState } from 'react';
import { createRootRoute, Outlet } from '@tanstack/react-router';
import { Sidebar } from '@/components/layout/sidebar';
import { TopBar } from '@/components/layout/top-bar';
import { DeploymentNotificationBar } from '@/components/primitives/deployment-notification-bar';
import { Providers } from '@/providers';

export const Route = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  return (
    <Providers>
      <AppShellFrame />
    </Providers>
  );
}

/**
 * App shell with top bar, sidebar, and main content area.
 * Handles responsive layout with mobile overlay menu.
 */
function AppShellFrame() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const toggleSidebar = () => {
    setSidebarCollapsed((prev) => !prev);
  };

  const toggleMobileMenu = () => {
    setMobileMenuOpen((prev) => !prev);
  };

  const handleNavigation = () => {
    setMobileMenuOpen(false);
  };

  // Determine which toggle to use based on viewport width.
  // On mobile (< lg breakpoint), toggle the mobile menu overlay.
  // On desktop (>= lg breakpoint), toggle the sidebar collapse state.
  const handleMenuToggle = () => {
    const isMobile = window.innerWidth < 1024;
    if (isMobile) {
      toggleMobileMenu();
    } else {
      toggleSidebar();
    }
  };

  return (
    <div
      className="flex h-screen flex-col overflow-hidden"
      data-testid="app-shell.root"
      data-mobile-menu-state={mobileMenuOpen ? 'open' : 'closed'}
    >
      {/* Deployment bar sits above everything */}
      <DeploymentNotificationBar />

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
        <main
          className="flex-1 overflow-auto"
          data-testid="app-shell.content"
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
