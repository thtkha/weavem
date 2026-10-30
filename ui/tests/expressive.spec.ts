import { expect, test } from './fixtures';

test('workbench layout preserves readable supported widths and the narrow export path', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  for (const width of [1100, 1280, 1600]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/');
    await expect(page.getByText('weavem', { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.setViewportSize({ width: 800, height: 900 });
  await expect(page.getByRole('region', { name: 'Desktop requirement' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Export draft', exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
