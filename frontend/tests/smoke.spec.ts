import { test, expect } from './support/fixtures';

test.describe('Smoke Tests', () => {
  test('frontend loads and shows app shell', async ({ page }) => {
    await page.goto('/');

    // Check page title
    await expect(page).toHaveTitle(/IoT Support/);

    // Check sidebar is visible
    const sidebar = page.getByTestId('app-shell.sidebar');
    await expect(sidebar).toBeVisible();

    // Check device configs link exists
    const devicesLink = page.getByTestId('app-shell.sidebar.link.devices');
    await expect(devicesLink).toBeVisible();
  });

  test('root redirects to /devices', async ({ page }) => {
    await page.goto('/');

    // Should redirect to /devices
    await expect(page).toHaveURL(/\/devices$/);

    // Should show device list page (either table or empty state)
    const heading = page.getByRole('heading', { name: 'Device Configs' });
    await expect(heading).toBeVisible();
  });

  test('backend health endpoint responds via proxy', async ({ request }) => {
    // Access backend through the Vite proxy
    const response = await request.get('/api/health');
    expect(response.ok()).toBeTruthy();
  });

  test('sidebar navigation shows active state', async ({ page }) => {
    await page.goto('/devices');

    // The devices link should show active state
    const devicesLink = page.getByTestId('app-shell.sidebar.link.devices');
    await expect(devicesLink).toHaveAttribute('data-active', 'true');
  });
});
