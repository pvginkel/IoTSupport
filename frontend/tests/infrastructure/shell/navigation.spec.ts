import { expect } from '@playwright/test';
import { test } from '../../support/fixtures-infrastructure';

test.describe('App shell - desktop navigation', () => {
  test('collapses sidebar and navigates primary routes', async ({
    appShell,
    page,
  }) => {
    await appShell.gotoHome();
    await expect(appShell.desktopSidebar).toBeVisible();
    await appShell.expectSidebarState('expanded');
    // Home redirects to /devices
    await expect(page).toHaveURL(/\/devices(?:$|\?)/);
    await appShell.expectActiveNav('devices');

    await appShell.toggleDesktopSidebar();
    await appShell.expectSidebarState('collapsed');
    await appShell.toggleDesktopSidebar();
    await appShell.expectSidebarState('expanded');

    await appShell.clickDesktopNav('device-models');
    await expect(page).toHaveURL(/\/device-models(?:$|\?)/);
    await appShell.expectActiveNav('device-models');

    await appShell.clickDesktopNav('devices');
    await expect(page).toHaveURL(/\/devices(?:$|\?)/);
    await appShell.expectActiveNav('devices');
  });

  test('renders Lucide icons for all navigation items', async ({ appShell, page }) => {
    await appShell.gotoHome();

    const navigationItems = ['device-models', 'devices', 'rotation'];

    for (const item of navigationItems) {
      const link = page.getByTestId(`app-shell.sidebar.link.${item}`);
      await expect(link).toBeVisible();
      const icon = link.locator('svg').first();
      await expect(icon).toBeVisible();
    }
  });
});
