import { expect, test } from '@playwright/test';

test('motion lab is opt-in, keyboard safe, and never runs or changes the editor graph', async ({ page }) => {
  const runs: string[] = [];
  page.on('request', (request) => { if (request.url().includes('/api/runs')) runs.push(request.url()); });
  await page.goto('/');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const trigger = page.getByRole('button', { name: 'Motion lab', exact: true });
  await trigger.click();
  const dialog = page.getByRole('dialog', { name: 'See a field become an input' });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('Illustrative design experiment');
  await dialog.getByRole('button', { name: 'Map email field' }).click();
  await expect(dialog.getByRole('status')).toContainText('customer.email');
  await expect(dialog.getByLabel('Illustrative target value')).toHaveText('"alex@example.test"');
  await dialog.getByRole('button', { name: 'Use whole result' }).click();
  await expect(dialog.getByRole('status')).toContainText('Whole result');
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await expect(page.getByTestId('task-node')).toHaveCount(3);
  await expect(page.locator('.react-flow__edge')).toHaveCount(2);
  expect(runs).toEqual([]);
});

test('motion lab retains a static working path when transitions are unavailable or motion is reduced', async ({ page }) => {
  await page.addInitScript(() => { Object.defineProperty(document, 'startViewTransition', { value: undefined, configurable: true }); });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await page.getByRole('button', { name: 'Motion lab', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'See a field become an input' });
  await expect(dialog).toContainText('Static transition');
  await dialog.getByRole('button', { name: 'Map email field' }).click();
  await expect(dialog.getByLabel('Illustrative target value')).toHaveText('"alex@example.test"');
  await dialog.getByRole('button', { name: 'Close motion lab' }).click();
  await expect(dialog).not.toBeVisible();
});

test('expressive layout preserves readable supported widths and the narrow export path', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  for (const width of [1100, 1280, 1600]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Motion lab', exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.setViewportSize({ width: 800, height: 900 });
  await expect(page.getByRole('region', { name: 'Desktop requirement' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Export draft', exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
