import { expect } from '@playwright/test';
import { test } from '../../support/fixtures';
import { SIDEBAR_VISIBLE } from '@/lib/consts';

const MOBILE_VIEWPORT = { width: 414, height: 736 } as const;

test.describe('App shell - mobile menu', () => {
  test.skip(!SIDEBAR_VISIBLE, 'Sidebar is hidden (SIDEBAR_VISIBLE = false)');


  test('opens, navigates, and closes the mobile sidebar', async ({
    appShell,
    page,
  }) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await appShell.gotoHome();

    await expect(appShell.desktopContainer).toBeHidden();
    await expect(appShell.hamburgerButton).toBeVisible();

    await appShell.openMobileMenu();
    await expect(appShell.mobileSidebar).toBeVisible();

    await appShell.sidebarLink('items', { variant: 'mobile' }).click();
    await appShell.expectMobileMenuState('closed');
    await expect(page).toHaveURL(/\/items(?:$|\?)/);

    await appShell.openMobileMenu();
    await appShell.closeMobileMenuViaBackdrop();
    await appShell.expectMobileMenuState('closed');

    await appShell.openMobileMenu();
    await appShell.sidebarLink('about', { variant: 'mobile' }).click();
    await appShell.expectMobileMenuState('closed');
    await expect(page).toHaveURL(/\/about(?:$|\?)/);
  });
});
