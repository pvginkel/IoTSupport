import { test, expect } from './support/fixtures';

test.describe('Smoke Tests', () => {
  test('frontend loads and shows app shell', async ({ page, auth }) => {
    // Authenticate first
    await auth.createSession({ name: 'Test User', roles: ['admin'] });

    await page.goto('/');

    // Check page title
    await expect(page).toHaveTitle(/IoT device management/);

    // Check sidebar is visible (on desktop)
    await page.setViewportSize({ width: 1280, height: 720 });
    const sidebar = page.getByTestId('app-shell.sidebar');
    await expect(sidebar).toBeVisible();

    // Check device configs link exists
    const devicesLink = page.getByTestId('app-shell.sidebar.link.devices');
    await expect(devicesLink).toBeVisible();
  });

  test('root redirects to /devices', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User', roles: ['admin'] });

    await page.goto('/');

    // Should redirect to /devices
    await expect(page).toHaveURL(/\/devices$/);

    // Should show device list page (either table or empty state)
    const heading = page.getByRole('heading', { name: 'Devices' });
    await expect(heading).toBeVisible();
  });

  test('backend health endpoint responds via proxy', async ({ request }) => {
    // Access backend through the Vite proxy
    const response = await request.get('/health/readyz');
    expect(response.ok()).toBeTruthy();
  });

  test('sidebar navigation shows active state', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User', roles: ['admin'] });

    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto('/devices');

    // The devices link should show active state
    const devicesLink = page.getByTestId('app-shell.sidebar.link.devices');
    await expect(devicesLink).toHaveAttribute('data-active', 'true');
  });
});
