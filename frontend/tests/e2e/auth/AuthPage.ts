/**
 * Page object for authentication-related test helpers.
 * Provides locators and actions for auth gate, top bar, user dropdown, and sidebar.
 */

import type { Page, Locator } from '@playwright/test'

export class AuthPage {
  constructor(private page: Page) {}

  // ============================================================================
  // Auth Gate Locators
  // ============================================================================

  /** Loading screen shown while checking authentication */
  get loadingScreen(): Locator {
    return this.page.locator('[data-testid="auth.gate.loading"]')
  }

  /** Error screen shown when auth check fails (non-401 errors) */
  get errorScreen(): Locator {
    return this.page.locator('[data-testid="auth.gate.error"]')
  }

  /** Retry button on error screen */
  get retryButton(): Locator {
    return this.page.locator('[data-testid="auth.gate.error.retry"]')
  }

  // ============================================================================
  // Top Bar Locators
  // ============================================================================

  /** Top bar container */
  get topBar(): Locator {
    return this.page.locator('[data-testid="app-shell.topbar"]')
  }

  /** Hamburger menu button */
  get hamburgerButton(): Locator {
    return this.page.locator('[data-testid="app-shell.topbar.hamburger"]')
  }

  /** Logo image */
  get logo(): Locator {
    return this.page.locator('[data-testid="app-shell.topbar.logo"]')
  }

  /** App title text */
  get title(): Locator {
    return this.page.locator('[data-testid="app-shell.topbar.title"]')
  }

  /** Home link (wraps logo and title) */
  get homeLink(): Locator {
    return this.page.locator('[data-testid="app-shell.topbar.home-link"]')
  }

  // ============================================================================
  // User Dropdown Locators
  // ============================================================================

  /** User dropdown trigger button */
  get userDropdownTrigger(): Locator {
    return this.page.locator('[data-testid="app-shell.topbar.user"]')
  }

  /** User name text inside dropdown trigger */
  get userName(): Locator {
    return this.page.locator('[data-testid="app-shell.topbar.user.name"]')
  }

  /** Dropdown menu container (only visible when open) */
  get userDropdownMenu(): Locator {
    return this.page.locator('[data-testid="app-shell.topbar.user.dropdown"]')
  }

  /** Logout button inside dropdown */
  get logoutButton(): Locator {
    return this.page.locator('[data-testid="app-shell.topbar.user.logout"]')
  }

  // ============================================================================
  // Sidebar Locators
  // ============================================================================

  /** Sidebar container */
  get sidebar(): Locator {
    return this.page.locator('[data-testid="app-shell.sidebar"]')
  }

  /** Mobile overlay backdrop */
  get mobileOverlay(): Locator {
    return this.page.locator('[data-testid="app-shell.mobile-overlay"]')
  }

  /** Mobile overlay dismiss area (backdrop click) */
  get mobileOverlayDismiss(): Locator {
    return this.page.locator('[data-testid="app-shell.mobile-overlay.dismiss"]')
  }

  // ============================================================================
  // Actions
  // ============================================================================

  /** Click the hamburger to toggle sidebar (desktop) or mobile menu */
  async toggleMenu(): Promise<void> {
    await this.hamburgerButton.click()
  }

  /** Open the user dropdown menu */
  async openUserDropdown(): Promise<void> {
    await this.userDropdownTrigger.click()
  }

  /** Click logout (dropdown must be open) */
  async clickLogout(): Promise<void> {
    await this.logoutButton.click()
  }

  /** Click retry on the error screen */
  async clickRetry(): Promise<void> {
    await this.retryButton.click()
  }

  /** Click the home link (logo + title) */
  async clickHomeLink(): Promise<void> {
    await this.homeLink.click()
  }

  /** Dismiss mobile overlay by clicking backdrop (click on right side to avoid sidebar) */
  async dismissMobileOverlay(): Promise<void> {
    // Click on the right side of the screen where the backdrop is visible
    // (sidebar is on the left side)
    await this.mobileOverlayDismiss.click({ position: { x: 350, y: 300 } })
  }

  // ============================================================================
  // Wait Helpers
  // ============================================================================

  /** Wait for auth loading screen to appear */
  async waitForLoadingScreen(): Promise<void> {
    await this.loadingScreen.waitFor({ state: 'visible' })
  }

  /** Wait for auth error screen to appear */
  async waitForErrorScreen(): Promise<void> {
    await this.errorScreen.waitFor({ state: 'visible' })
  }

  /** Wait for top bar to be visible (indicates auth completed successfully) */
  async waitForAuthenticated(): Promise<void> {
    await this.topBar.waitFor({ state: 'visible' })
  }

  /** Wait for user dropdown menu to appear */
  async waitForDropdownOpen(): Promise<void> {
    await this.userDropdownMenu.waitFor({ state: 'visible' })
  }

  /** Wait for user dropdown menu to close */
  async waitForDropdownClosed(): Promise<void> {
    await this.userDropdownMenu.waitFor({ state: 'hidden' })
  }

  // ============================================================================
  // State Queries
  // ============================================================================

  /** Get the current user display name */
  async getUserName(): Promise<string> {
    return (await this.userName.textContent()) ?? ''
  }

  /** Check if sidebar is collapsed (desktop) */
  async isSidebarCollapsed(): Promise<boolean> {
    const state = await this.sidebar.getAttribute('data-state')
    return state === 'collapsed'
  }

  /** Check if mobile menu is open */
  async isMobileMenuOpen(): Promise<boolean> {
    const root = this.page.locator('[data-testid="app-shell.root"]')
    const state = await root.getAttribute('data-mobile-menu-state')
    return state === 'open'
  }
}
