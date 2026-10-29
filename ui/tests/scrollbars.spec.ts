import { expect, test, type Locator } from '@playwright/test';
import { readFile } from 'node:fs/promises';

// Headless Chromium hides native scrollbars by default, including their hit targets.
test.use({ launchOptions: { ignoreDefaultArgs: ['--hide-scrollbars'] } });

async function expectCustomScrollbar(element: Locator) {
  expect(await element.evaluate((el) => {
    const bar = getComputedStyle(el, '::-webkit-scrollbar');
    const thumb = getComputedStyle(el, '::-webkit-scrollbar-thumb');
    return { width: bar.width, height: bar.height, color: thumb.backgroundColor, radius: thumb.borderRadius };
  })).toEqual({ width: '6px', height: '6px', color: 'rgb(94, 112, 74)', radius: '999px' });
}

test('panels and JSON fields retain native scrolling with matching slim scrollbars', async ({ page }, info) => {
  await page.setViewportSize({ width: 1400, height: 650 });
  await page.goto('/');
  const library = page.getByRole('complementary', { name: 'Task library' });
  const inspector = page.getByRole('complementary', { name: 'Node inspector' });
  await page.locator('[data-node-id="demo-normalize"]').click();
  const parameters = page.getByRole('textbox', { name: 'Draft parameters', exact: true });
  await parameters.fill(JSON.stringify(Object.fromEntries(Array.from({ length: 60 }, (_, i) => [`field${i}`, 'value '.repeat(60)])), null, 2));
  await parameters.evaluate((el) => el.setAttribute('wrap', 'off'));
  for (const element of [library, inspector, parameters]) {
    await expectCustomScrollbar(element);
    expect(await element.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  }
  // Wheel scrolling, keyboard editing and thumb dragging stay browser-owned.
  await library.hover(); await page.mouse.wheel(0, 300);
  await expect.poll(() => library.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  await parameters.focus(); await parameters.press('Control+Home'); await parameters.press('Control+End');
  await expect.poll(() => parameters.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  await parameters.evaluate((el) => { el.scrollLeft = 100; });
  expect(await parameters.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
  await inspector.evaluate((el) => { el.scrollTop = 0; });
  const box = (await inspector.boundingBox())!;
  const thumbHeight = await inspector.evaluate((el) => el.clientHeight * el.clientHeight / el.scrollHeight);
  await page.mouse.move(box.x + box.width - 3, box.y + Math.min(thumbHeight / 2, 30));
  await page.mouse.down(); await page.mouse.move(box.x + box.width - 3, box.y + 180, { steps: 10 }); await page.mouse.up();
  await expect.poll(() => inspector.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  await page.screenshot({ path: info.outputPath('custom-scrollbars.png'), fullPage: true });
  await page.getByRole('separator', { name: 'Resize inspector', exact: true }).focus();
  await page.keyboard.press('Home');
  expect(await inspector.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
});

test('run logs use the same scrollbar and forced colors restore system styling', async ({ page }) => {
  const metadata = JSON.parse(await readFile(new URL('./metadata.json', import.meta.url), 'utf8'));
  await page.route('**/api/session', (route) => route.fulfill({ json: {
    token: 'test-token', project: '/projects/document-demo', metadata,
    bindings: Object.fromEntries(metadata.tasks.map((task: { path: string }) => [`local:${task.path}`, 'normalize'])),
  } }));
  await page.route('**/api/runs', (route) => route.fulfill({ json: { runId: 'scroll-test', status: 'running' } }));
  await page.route('**/api/runs/scroll-test', (route) => route.fulfill({ json: {
    runId: 'scroll-test', status: 'completed', nodes: {}, logs: 'A line of output\n'.repeat(100),
  } }));
  await page.goto('/');
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  await page.getByRole('button', { name: 'Replace draft', exact: true }).click();
  await page.getByRole('button', { name: 'Add task text.normalize', exact: true }).first().click();
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Run flow', exact: true }).click();
  const log = page.getByRole('region', { name: 'Run log', exact: true });
  await expect(log).toContainText('A line of output');
  await expectCustomScrollbar(log);
  await log.hover(); await page.mouse.wheel(0, 400);
  await expect.poll(() => log.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  await page.emulateMedia({ forcedColors: 'active' });
  for (const element of [log, page.getByRole('complementary', { name: 'Node inspector' })]) {
    await expect(element).toHaveCSS('scrollbar-color', 'auto');
    await expect(element).toHaveCSS('scrollbar-width', 'auto');
    expect(await element.evaluate((el) => getComputedStyle(el, '::-webkit-scrollbar').width)).toBe('auto');
  }
});
