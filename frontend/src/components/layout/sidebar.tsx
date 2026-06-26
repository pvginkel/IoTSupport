/**
 * Sidebar component.
 * Navigation-only component (header moved to TopBar).
 * Collapses to icon-only (w-16) when toggled on desktop.
 * Supports grouped navigation items via optional children array.
 */

import { Link, useLocation } from '@tanstack/react-router'
import type { LucideIcon } from 'lucide-react'
import { navigationItems } from './sidebar-nav'

export interface SidebarItem {
  to: string
  label: string
  icon: LucideIcon
  testId: string
  children?: SidebarItem[]
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
 *
 * Grouped items:
 * - Items with `children` render their children indented below the parent
 * - In collapsed mode, children are hidden (routes remain accessible via URL)
 * - Parent shows active styling when any child route is active
 */
export function Sidebar({
  isCollapsed = false,
  onNavigate,
  variant = 'desktop'
}: SidebarProps) {
  const dataState = isCollapsed ? 'collapsed' : 'expanded'
  const location = useLocation()

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
            {navigationItems.map((item) => {
              // Check if any child route is active (for parent highlight)
              const isChildActive = item.children?.some(
                (child) => location.pathname.startsWith(child.to)
              ) ?? false

              return (
                <li key={item.to} data-testid={`app-shell.sidebar.item.${item.testId}`}>
                  <Link
                    to={item.to}
                    className={`flex items-center rounded-md py-2 text-sm transition-colors hover:bg-accent hover:text-accent-foreground [&.active]:bg-accent [&.active]:text-accent-foreground [&.active]:font-medium ${isCollapsed ? 'justify-center px-2' : 'gap-3 px-3'} ${isChildActive ? 'bg-accent text-accent-foreground font-medium' : ''}`}
                    data-testid={`app-shell.sidebar.link.${item.testId}`}
                    data-nav-target={item.to}
                    title={item.label}
                    activeProps={{
                      className: 'active',
                      'data-active': 'true',
                      'aria-current': 'page',
                    }}
                    inactiveProps={{ 'data-active': isChildActive ? 'true' : 'false' }}
                    onClick={() => onNavigate?.()}
                  >
                    <item.icon className="h-5 w-5" aria-hidden="true" />
                    {!isCollapsed && <span>{item.label}</span>}
                  </Link>

                  {/* Render children indented below the parent (hidden when collapsed) */}
                  {item.children && !isCollapsed && (
                    <ul className="mt-1 space-y-1">
                      {item.children.map((child) => (
                        <li key={child.to} data-testid={`app-shell.sidebar.item.${child.testId}`}>
                          <Link
                            to={child.to}
                            className="flex items-center gap-3 rounded-md py-2 pl-8 pr-3 text-sm transition-colors text-muted-foreground hover:bg-accent hover:text-accent-foreground [&.active]:bg-accent [&.active]:text-accent-foreground [&.active]:font-medium"
                            data-testid={`app-shell.sidebar.link.${child.testId}`}
                            data-nav-target={child.to}
                            title={child.label}
                            activeProps={{
                              className: 'active',
                              'data-active': 'true',
                              'aria-current': 'page',
                            }}
                            inactiveProps={{ 'data-active': 'false' }}
                            onClick={() => onNavigate?.()}
                          >
                            <child.icon className="h-4 w-4" aria-hidden="true" />
                            <span>{child.label}</span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              )
            })}
          </ul>
        </nav>
      </div>
    </div>
  )
}
