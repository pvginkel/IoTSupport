/**
 * Sidebar component.
 * Navigation-only component (header moved to TopBar).
 * Collapses to icon-only (w-20) when toggled on desktop.
 */

import { Link } from '@tanstack/react-router'
import type { LucideIcon } from 'lucide-react'
import { navigationItems } from './sidebar-nav'

export interface SidebarItem {
  to: string
  label: string
  icon: LucideIcon
  testId: string
}

interface SidebarProps {
  isCollapsed?: boolean
  onNavigate?: () => void
  variant?: 'desktop' | 'mobile'
}

/**
 * Sidebar component.
 * Renders navigation links only - header content is now in TopBar.
 *
 * Collapse behavior:
 * - Desktop: Shows icons only (w-16) when collapsed, full width (w-64) when expanded
 * - Mobile: Always shows full width in overlay
 */
export function Sidebar({
  isCollapsed = false,
  onNavigate,
  variant = 'desktop'
}: SidebarProps) {
  const dataState = isCollapsed ? 'collapsed' : 'expanded'

  return (
    <div
      className={`bg-background border-r border-border transition-all duration-300 h-full ${isCollapsed ? 'w-16' : 'w-64'}`}
      data-testid="app-shell.sidebar"
      data-state={dataState}
      data-variant={variant}
    >
      <div className="flex h-full flex-col">
        {/* Navigation */}
        <nav
          className="flex-1 overflow-y-auto py-4"
          aria-label="Primary"
          data-testid="app-shell.sidebar.nav"
        >
          <ul className="space-y-2 px-3">
            {navigationItems.map((item) => (
              <li key={item.to} data-testid={`app-shell.sidebar.item.${item.testId}`}>
                <Link
                  to={item.to}
                  className={`flex items-center rounded-md py-2 text-sm transition-colors hover:bg-accent hover:text-accent-foreground [&.active]:bg-accent [&.active]:text-accent-foreground [&.active]:font-medium ${isCollapsed ? 'justify-center px-2' : 'gap-3 px-3'}`}
                  data-testid={`app-shell.sidebar.link.${item.testId}`}
                  data-nav-target={item.to}
                  title={item.label}
                  activeProps={{
                    className: 'active',
                    'data-active': 'true',
                    'aria-current': 'page',
                  }}
                  inactiveProps={{ 'data-active': 'false' }}
                  onClick={() => onNavigate?.()}
                >
                  <item.icon className="h-5 w-5" aria-hidden="true" />
                  {!isCollapsed && <span>{item.label}</span>}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </div>
  )
}
