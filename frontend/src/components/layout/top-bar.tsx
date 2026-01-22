/**
 * TopBar component.
 * Displays hamburger menu, logo, app title, and user dropdown.
 * Layout: hamburger | logo | "IoT Support" | spacer | user dropdown
 */

import { Link } from '@tanstack/react-router'
import { UserDropdown } from './user-dropdown'

interface TopBarProps {
  onMenuToggle: () => void
  isMobile?: boolean
}

/**
 * TopBar component.
 * Provides app header with navigation toggle and user controls.
 */
export function TopBar({ onMenuToggle, isMobile = false }: TopBarProps) {
  return (
    <header
      className="flex h-14 items-center border-b border-zinc-800 bg-zinc-950 px-4"
      data-testid="app-shell.topbar"
    >
      {/* Hamburger menu button */}
      <button
        type="button"
        onClick={onMenuToggle}
        className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-900 hover:text-zinc-50 transition-colors"
        aria-label={isMobile ? 'Toggle mobile menu' : 'Toggle sidebar'}
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

      {/* Logo and title - links to home */}
      <Link
        to="/"
        className="ml-3 flex items-center gap-2 text-zinc-50 hover:text-zinc-200 transition-colors text-xl"
        data-testid="app-shell.topbar.home-link"
      >
        {/* Logo - 110% of text height via em units inherited from parent font-size */}
        <img
          src="/favicon.png"
          alt="IoT Support Logo"
          className="h-[1.4em] w-[1.4em] mr-1 mt-1"
          data-testid="app-shell.topbar.logo"
        />
        <span
          className="font-semibold"
          data-testid="app-shell.topbar.title"
        >
          IoT Support
        </span>
      </Link>

      {/* Spacer */}
      <div className="flex-1" />

      {/* User dropdown */}
      <UserDropdown />
    </header>
  )
}
