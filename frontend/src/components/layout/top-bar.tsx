/**
 * TopBar component.
 * Displays hamburger menu (when sidebar enabled), logo, app title, and user dropdown.
 * Layout: [hamburger] | logo | title | spacer | user dropdown
 */

import { Link } from '@tanstack/react-router'
import { PROJECT_TITLE, PROJECT_DESCRIPTION } from '@/lib/consts'
import { UserDropdown } from './user-dropdown'

interface TopBarProps {
  /** When provided, renders a hamburger menu button. Omit to hide the hamburger. */
  onMenuToggle?: () => void
}

/**
 * TopBar component.
 * Provides app header with optional navigation toggle and user controls.
 */
export function TopBar({ onMenuToggle }: TopBarProps) {
  return (
    <header
      className="flex h-14 items-center border-b border-border bg-background px-4"
      data-testid="app-shell.topbar"
    >
      {/* Hamburger menu button - only shown when sidebar is enabled */}
      {onMenuToggle && (
        <button
          type="button"
          onClick={onMenuToggle}
          className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          aria-label="Toggle navigation menu"
          data-testid="app-shell.topbar.hamburger"
        >
          <svg
            className="h-5 w-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 6h16M4 12h16M4 18h16"
            />
          </svg>
        </button>
      )}

      {/* Logo and title - links to home */}
      <Link
        to="/"
        className={`${onMenuToggle ? 'ml-3 ' : ''}flex items-center gap-2 text-foreground hover:text-primary transition-colors text-xl`}
        data-testid="app-shell.topbar.home-link"
      >
        {/* Logo - 110% of text height via em units inherited from parent font-size */}
        <img
          src="/favicon.png"
          alt={`${PROJECT_DESCRIPTION} Logo`}
          className="h-[1.4em] w-[1.4em] mr-1 mt-1"
          data-testid="app-shell.topbar.logo"
        />
        <span
          className="font-semibold"
          data-testid="app-shell.topbar.title"
        >
          {PROJECT_TITLE}
        </span>
      </Link>

      {/* Spacer */}
      <div className="flex-1" />

      {/* User dropdown */}
      <UserDropdown />
    </header>
  )
}
