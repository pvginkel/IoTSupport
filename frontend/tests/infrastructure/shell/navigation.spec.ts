import { expect } from '@playwright/test';
import { test } from '../../support/fixtures';
import { SIDEBAR_VISIBLE } from '@/lib/consts';

test.describe('App shell - desktop navigation', () => {
  test.skip(!SIDEBAR_VISIBLE, 'Sidebar is hidden (SIDEBAR_VISIBLE = false)');


  test('collapses sidebar and navigates primary routes', async ({
    appShell,
    page,
  }) => {
    await appShell.gotoHome();
    await expect(appShell.desktopSidebar).toBeVisible();
    await appShell.expectSidebarState('expanded');
    // Home redirects to /items
    await expect(page).toHaveURL(/\/items(?:$|\?)/);
    await appShell.expectActiveNav('items');

    await appShell.toggleDesktopSidebar();
    await appShell.expectSidebarState('collapsed');
    await appShell.toggleDesktopSidebar();
    await appShell.expectSidebarState('expanded');

    await appShell.clickDesktopNav('about');
    await expect(page).toHaveURL(/\/about(?:$|\?)/);
    await appShell.expectActiveNav('about');

    await appShell.clickDesktopNav('items');
    await expect(page).toHaveURL(/\/items(?:$|\?)/);
    await appShell.expectActiveNav('items');
  });

  test('renders Lucide icons for all navigation items', async ({ appShell, page }) => {
    await appShell.gotoHome();

    const navigationItems = ['items', 'about'];

    for (const item of navigationItems) {
      const link = page.getByTestId(`app-shell.sidebar.link.${item}`);
      await expect(link).toBeVisible();
      const icon = link.locator('svg').first();
      await expect(icon).toBeVisible();
    }
  });
});
