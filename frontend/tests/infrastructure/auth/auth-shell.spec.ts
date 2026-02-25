/**
 * App Shell Layout Tests
 *
 * Tests for sidebar toggle, mobile menu, and top bar layout.
 * Requires use_app_shell=true (excluded when use_app_shell=false).
 */

import { test, expect } from '../../support/fixtures'
import { AuthPage } from './AuthPage'

test.describe('App Shell Layout', () => {
  test.describe('Sidebar Toggle (Desktop)', () => {
    test('collapses sidebar when hamburger clicked', async ({ page, auth }) => {
      await auth.createSession({ name: 'Sidebar User' })

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
      await auth.createSession({ name: 'Sidebar User' })

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
    test('opens overlay menu on mobile when hamburger clicked', async ({ page, auth }) => {
      await auth.createSession({ name: 'Mobile User' })

      await page.setViewportSize({ width: 375, height: 667 })
      await page.goto('/')

      const authPage = new AuthPage(page)
      await authPage.waitForAuthenticated()

      await expect(authPage.mobileOverlay).not.toBeVisible()

      await authPage.toggleMenu()

      await expect(authPage.mobileOverlay).toBeVisible()
    })

    test('closes overlay when clicking outside', async ({ page, auth }) => {
      await auth.createSession({ name: 'Mobile User' })

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
    test('shows hamburger, logo, title, and user dropdown in correct order', async ({ page, auth }) => {
      await auth.createSession({ name: 'Layout User' })

      await page.goto('/')

      const authPage = new AuthPage(page)
      await authPage.waitForAuthenticated()

      await expect(authPage.hamburgerButton).toBeVisible()
      await expect(authPage.logo).toBeVisible()
      await expect(authPage.title).toBeVisible()
      await expect(authPage.userDropdownTrigger).toBeVisible()

      const hamburgerBox = await authPage.hamburgerButton.boundingBox()
      const logoBox = await authPage.logo.boundingBox()
      const titleBox = await authPage.title.boundingBox()
      const userBox = await authPage.userDropdownTrigger.boundingBox()

      expect(hamburgerBox).not.toBeNull()
      expect(logoBox).not.toBeNull()
      expect(titleBox).not.toBeNull()
      expect(userBox).not.toBeNull()

      expect(hamburgerBox!.x).toBeLessThan(logoBox!.x)
      expect(logoBox!.x).toBeLessThan(titleBox!.x)
      expect(titleBox!.x).toBeLessThan(userBox!.x)
    })

  })
})
