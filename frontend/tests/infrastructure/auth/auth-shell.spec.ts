/**
 * App Shell Layout Tests
 *
 * Tests for sidebar toggle, mobile menu, and top bar layout.
 * Requires use_app_shell=true (excluded when use_app_shell=false).
 */

import { test, expect } from '../../support/fixtures'
import { AuthPage } from './AuthPage'
import { SIDEBAR_VISIBLE } from '../../../src/lib/consts'

test.describe('App Shell Layout', () => {
  test.describe('Sidebar Toggle (Desktop)', () => {
    // Skip sidebar tests when the app hides the sidebar (SIDEBAR_VISIBLE = false)
    test.skip(!SIDEBAR_VISIBLE, 'Sidebar is not visible in this app')

    test('collapses sidebar when hamburger clicked', async ({ page, auth }) => {
      await auth.createSession({ name: 'Sidebar User', roles: ['editor'] })

      await page.setViewportSize({ width: 1280, height: 720 })
      await page.goto('/')

      const authPage = new AuthPage(page)
      await authPage.waitForAuthenticated()

      await expect(authPage.sidebar).toBeVisible()
      expect(await authPage.isSidebarCollapsed()).toBe(false)

      await authPage.toggleMenu()

      expect(await authPage.isSidebarCollapsed()).toBe(true)
    })

    test('expands sidebar when hamburger clicked again', async ({ page, auth }) => {
      await auth.createSession({ name: 'Sidebar User', roles: ['editor'] })

      await page.setViewportSize({ width: 1280, height: 720 })
      await page.goto('/')

      const authPage = new AuthPage(page)
      await authPage.waitForAuthenticated()

      await authPage.toggleMenu()
      expect(await authPage.isSidebarCollapsed()).toBe(true)

      await authPage.toggleMenu()
      expect(await authPage.isSidebarCollapsed()).toBe(false)
    })
  })

  test.describe('Mobile Menu Toggle', () => {
    test.skip(!SIDEBAR_VISIBLE, 'Sidebar is not visible in this app')

    test('opens overlay menu on mobile when hamburger clicked', async ({ page, auth }) => {
      await auth.createSession({ name: 'Mobile User', roles: ['editor'] })

      await page.setViewportSize({ width: 375, height: 667 })
      await page.goto('/')

      const authPage = new AuthPage(page)
      await authPage.waitForAuthenticated()

      await expect(authPage.mobileOverlay).not.toBeVisible()

      await authPage.toggleMenu()

      await expect(authPage.mobileOverlay).toBeVisible()
    })

    test('closes overlay when clicking outside', async ({ page, auth }) => {
      await auth.createSession({ name: 'Mobile User', roles: ['editor'] })

      await page.setViewportSize({ width: 375, height: 667 })
      await page.goto('/')

      const authPage = new AuthPage(page)
      await authPage.waitForAuthenticated()

      await authPage.toggleMenu()
      await expect(authPage.mobileOverlay).toBeVisible()

      await authPage.dismissMobileOverlay()

      await expect(authPage.mobileOverlay).not.toBeVisible()
    })
  })

  test.describe('Top Bar Layout', () => {
    test('shows logo, title, and user dropdown in correct order', async ({ page, auth }) => {
      await auth.createSession({ name: 'Layout User', roles: ['editor'] })

      await page.goto('/')

      const authPage = new AuthPage(page)
      await authPage.waitForAuthenticated()

      await expect(authPage.logo).toBeVisible()
      await expect(authPage.title).toBeVisible()
      await expect(authPage.userDropdownTrigger).toBeVisible()

      const logoBox = await authPage.logo.boundingBox()
      const titleBox = await authPage.title.boundingBox()
      const userBox = await authPage.userDropdownTrigger.boundingBox()

      expect(logoBox).not.toBeNull()
      expect(titleBox).not.toBeNull()
      expect(userBox).not.toBeNull()

      expect(logoBox!.x).toBeLessThan(titleBox!.x)
      expect(titleBox!.x).toBeLessThan(userBox!.x)

      if (SIDEBAR_VISIBLE) {
        await expect(authPage.hamburgerButton).toBeVisible()
        const hamburgerBox = await authPage.hamburgerButton.boundingBox()
        expect(hamburgerBox).not.toBeNull()
        expect(hamburgerBox!.x).toBeLessThan(logoBox!.x)
      }
    })

  })
})
