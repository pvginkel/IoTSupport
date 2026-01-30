/**
 * Sidebar component.
 * Navigation-only component (header moved to TopBar).
 * Collapses completely (0 width) when toggled.
 */

import { Link } from '@tanstack/react-router'
import { Settings, Box, RefreshCw, type LucideIcon } from 'lucide-react'

interface SidebarItem {
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

const navigationItems: SidebarItem[] = [
  { to: '/device-models', label: 'Device Models', icon: Box, testId: 'device-models' },
  { to: '/devices', label: 'Devices', icon: Settings, testId: 'devices' },
  { to: '/rotation', label: 'Rotation Dashboard', icon: RefreshCw, testId: 'rotation' },
]

/**
 * Sidebar component.
 * Renders navigation links only - header content is now in TopBar.
 *
 * Collapse behavior:
 * - Desktop: Fully hides (0 width) when collapsed
 * - Mobile: Always shows full width in overlay
 */
export function Sidebar({
  isCollapsed = false,
  onNavigate,
  variant = 'desktop',
}: SidebarProps) {
  const dataState = isCollapsed ? 'collapsed' : 'expanded'

  // Desktop sidebar collapses to 0 width; mobile always shows full
  const widthClass = variant === 'mobile'
    ? 'w-64'
    : isCollapsed
      ? 'w-0 overflow-hidden'
      : 'w-64'

  return (
    <div
      className={`bg-background border-r border-border transition-all duration-300 h-full ${widthClass}`}
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
            {navigationItems.map(item => (
              <li key={item.to} data-testid={`app-shell.sidebar.item.${item.testId}`}>
                <Link
                  to={item.to}
                  className="flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors text-muted-foreground hover:bg-secondary hover:text-foreground [&.active]:bg-secondary [&.active]:text-foreground [&.active]:font-medium whitespace-nowrap"
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
                  <item.icon className="h-5 w-5 shrink-0" aria-hidden="true" />
                  <span>{item.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </div>
  )
}
