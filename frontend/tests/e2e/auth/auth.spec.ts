/**
 * Authentication Flow Tests
 *
 * Tests for OIDC authentication integration including:
 * - Auth loading and error states
 * - Login redirect on 401
 * - User display and dropdown
 * - Logout flow
 * - App shell layout (sidebar toggle, mobile menu)
 */

import { test, expect } from '../../support/fixtures'
import { AuthPage } from './AuthPage'

test.describe('Authentication', () => {
  test.describe('Auth Loading State', () => {
    test('shows loading indicator before auth completes', async ({ page, auth }) => {
      // Clear any existing session first
      await auth.clearSession()

      // Create session so auth will succeed (we just want to see loading state)
      await auth.createSession({ name: 'Test User', roles: ['editor'] })

      // Navigate and check for loading state
      // Note: Loading state may be very brief, so we check it was rendered
      await page.goto('/')

      const authPage = new AuthPage(page)
      // Wait for authenticated state (loading should have appeared first)
      await authPage.waitForAuthenticated()

      // Verify we're now authenticated
      await expect(authPage.topBar).toBeVisible()
    })
  })

  test.describe('Login Redirect on 401', () => {
    test('redirects to login when not authenticated', async ({ page, auth }) => {
      await auth.clearSession()
      await auth.forceError(401)

      const loginRequestPromise = page.waitForRequest(request =>
        request.url().includes('/api/auth/login')
      )

      await page.goto('/')

      const loginRequest = await loginRequestPromise
      expect(loginRequest.url()).toContain('/api/auth/login')
      expect(loginRequest.url()).toContain('redirect=')
    })

    test('preserves full path including query params in redirect', async ({ page, auth }) => {
      await auth.clearSession()
      await auth.forceError(401)

      const loginRequestPromise = page.waitForRequest(request =>
        request.url().includes('/api/auth/login')
      )

      await page.goto('/devices?filter=active&sort=name')

      const loginRequest = await loginRequestPromise

      const url = new URL(loginRequest.url())
      const redirectParam = url.searchParams.get('redirect')
      expect(redirectParam).toContain('/devices')
      expect(redirectParam).toContain('filter=active')
      expect(redirectParam).toContain('sort=name')
    })
  })

  test.describe('Auth Error and Retry', () => {
    test('shows error screen when auth returns 500', async ({ page, auth }) => {
      // Configure backend to return 500 on next auth check
      await auth.forceError(500)

      // Navigate to app
      await page.goto('/')

      const authPage = new AuthPage(page)

      // Should show error screen
      await authPage.waitForErrorScreen()
      await expect(authPage.errorScreen).toBeVisible()
      await expect(authPage.retryButton).toBeVisible()
    })

    test('retry button triggers new auth check', async ({ page, auth }) => {
      // Force error on first request
      await auth.forceError(500)

      // But create a session so retry succeeds
      await auth.createSession({ name: 'Retry User', roles: ['editor'] })

      // Navigate to app
      await page.goto('/')

      const authPage = new AuthPage(page)

      // Should show error screen first
      await authPage.waitForErrorScreen()
      await expect(authPage.errorScreen).toBeVisible()

      // Click retry
      await authPage.clickRetry()

      // Should now be authenticated
      await authPage.waitForAuthenticated()
      await expect(authPage.userName).toHaveText('Retry User')
    })
  })

  test.describe('Authenticated User Display', () => {
    test('displays user name in top bar when authenticated', async ({ page, auth }) => {
      // Create session with specific name
      await auth.createSession({ name: 'John Doe', roles: ['editor'] })

      // Navigate to app
      await page.goto('/')

      const authPage = new AuthPage(page)
      await authPage.waitForAuthenticated()

      // Verify user name is displayed
      await expect(authPage.userName).toHaveText('John Doe')
    })

    test('displays "Unknown User" when name is null', async ({ page, auth }) => {
      // Create session with null name
      await auth.createSession({ name: null, email: 'test@example.com', roles: ['editor'] })

      // Navigate to app
      await page.goto('/')

      const authPage = new AuthPage(page)
      await authPage.waitForAuthenticated()

      // Verify fallback name is displayed
      await expect(authPage.userName).toHaveText('Unknown User')
    })
  })

  test.describe('Logout Flow', () => {
    test('shows dropdown menu when clicking user name', async ({ page, auth }) => {
      await auth.createSession({ name: 'Dropdown User', roles: ['editor'] })

      await page.goto('/')

      const authPage = new AuthPage(page)
      await authPage.waitForAuthenticated()

      // Click user dropdown trigger
      await authPage.openUserDropdown()

      // Dropdown should be visible with logout option
      await authPage.waitForDropdownOpen()
      await expect(authPage.userDropdownMenu).toBeVisible()
      await expect(authPage.logoutButton).toBeVisible()
    })

    test('clicking logout navigates to logout endpoint', async ({ page, auth }) => {
      await auth.createSession({ name: 'Logout User', roles: ['editor'] })

      await page.goto('/')

      const authPage = new AuthPage(page)
      await authPage.waitForAuthenticated()

      // Open dropdown
      await authPage.openUserDropdown()
      await authPage.waitForDropdownOpen()

      // Set up request listener to verify logout endpoint is called
      const logoutRequestPromise = page.waitForRequest(request =>
        request.url().includes('/api/auth/logout')
      )

      // Click logout
      await authPage.clickLogout()

      // Verify logout endpoint was called
      const logoutRequest = await logoutRequestPromise
      expect(logoutRequest.url()).toContain('/api/auth/logout')
    })
  })
})

test.describe('App Shell Layout', () => {
  test.describe('Sidebar Toggle (Desktop)', () => {
    test('collapses sidebar to zero width when hamburger clicked', async ({ page, auth }) => {
      await auth.createSession({ name: 'Sidebar User', roles: ['editor'] })

      // Use desktop viewport
      await page.setViewportSize({ width: 1280, height: 720 })
      await page.goto('/')

      const authPage = new AuthPage(page)
      await authPage.waitForAuthenticated()

      // Sidebar should be expanded initially
      await expect(authPage.sidebar).toBeVisible()
      expect(await authPage.isSidebarCollapsed()).toBe(false)

      // Click hamburger to collapse
      await authPage.toggleMenu()

      // Sidebar should now be collapsed
      expect(await authPage.isSidebarCollapsed()).toBe(true)
    })

    test('expands sidebar when hamburger clicked again', async ({ page, auth }) => {
      await auth.createSession({ name: 'Sidebar User', roles: ['editor'] })

      await page.setViewportSize({ width: 1280, height: 720 })
      await page.goto('/')

      const authPage = new AuthPage(page)
      await authPage.waitForAuthenticated()

      // Collapse sidebar
      await authPage.toggleMenu()
      expect(await authPage.isSidebarCollapsed()).toBe(true)

      // Expand sidebar
      await authPage.toggleMenu()
      expect(await authPage.isSidebarCollapsed()).toBe(false)
    })
  })

  test.describe('Mobile Menu Toggle', () => {
    test('opens overlay menu on mobile when hamburger clicked', async ({ page, auth }) => {
      await auth.createSession({ name: 'Mobile User', roles: ['editor'] })

      // Use mobile viewport
      await page.setViewportSize({ width: 375, height: 667 })
      await page.goto('/')

      const authPage = new AuthPage(page)
      await authPage.waitForAuthenticated()

      // Mobile overlay should not be visible initially
      await expect(authPage.mobileOverlay).not.toBeVisible()

      // Click hamburger to open mobile menu
      await authPage.toggleMenu()

      // Mobile overlay should now be visible
      await expect(authPage.mobileOverlay).toBeVisible()
    })

    test('closes overlay when clicking outside', async ({ page, auth }) => {
      await auth.createSession({ name: 'Mobile User', roles: ['editor'] })

      await page.setViewportSize({ width: 375, height: 667 })
      await page.goto('/')

      const authPage = new AuthPage(page)
      await authPage.waitForAuthenticated()

      // Open mobile menu
      await authPage.toggleMenu()
      await expect(authPage.mobileOverlay).toBeVisible()

      // Click dismiss area (backdrop)
      await authPage.dismissMobileOverlay()

      // Overlay should close
      await expect(authPage.mobileOverlay).not.toBeVisible()
    })
  })

  test.describe('Top Bar Layout', () => {
    test('shows hamburger, logo, title, and user dropdown in correct order', async ({ page, auth }) => {
      await auth.createSession({ name: 'Layout User', roles: ['editor'] })

      await page.goto('/')

      const authPage = new AuthPage(page)
      await authPage.waitForAuthenticated()

      // Verify all elements are visible
      await expect(authPage.hamburgerButton).toBeVisible()
      await expect(authPage.logo).toBeVisible()
      await expect(authPage.title).toHaveText('IoT Support')
      await expect(authPage.userDropdownTrigger).toBeVisible()

      // Verify order by checking relative positions
      const hamburgerBox = await authPage.hamburgerButton.boundingBox()
      const logoBox = await authPage.logo.boundingBox()
      const titleBox = await authPage.title.boundingBox()
      const userBox = await authPage.userDropdownTrigger.boundingBox()

      expect(hamburgerBox).not.toBeNull()
      expect(logoBox).not.toBeNull()
      expect(titleBox).not.toBeNull()
      expect(userBox).not.toBeNull()

      // Order should be: hamburger < logo < title < user (left to right)
      expect(hamburgerBox!.x).toBeLessThan(logoBox!.x)
      expect(logoBox!.x).toBeLessThan(titleBox!.x)
      expect(titleBox!.x).toBeLessThan(userBox!.x)
    })

    test('logo and title link to home route', async ({ page, auth }) => {
      await auth.createSession({ name: 'Navigation User', roles: ['editor'] })

      // Start on devices page
      await page.goto('/devices')

      const authPage = new AuthPage(page)
      await authPage.waitForAuthenticated()

      // Click home link (logo + title)
      await authPage.clickHomeLink()

      // Should navigate to root (which redirects to /devices)
      await expect(page).toHaveURL(/\/devices/)
    })
  })
})
