import { expect, test } from '@playwright/test';

test('selected Expressive composition uses the approved olive palette on rendered surfaces', async ({ page }) => {
  await page.goto('/');
  await page.locator('[data-node-id="demo-normalize"]').click();
  const colors = await page.evaluate(() => {
    const color = (selector: string, property: 'backgroundColor' | 'color' | 'borderTopColor') => getComputedStyle(document.querySelector(selector)!)[property];
    return {
      canvas: color('.canvas-area', 'backgroundColor'),
      panel: color('.inspector', 'backgroundColor'),
      task: color('.task-node', 'backgroundColor'),
      run: color('.run-actions button', 'backgroundColor'),
      runInk: color('.run-actions button', 'color'),
      metadata: color('.field-help', 'color'),
      inputBorder: color('.toolbar-flow-name input', 'borderTopColor'),
    };
  });
  expect(colors).toEqual({ canvas: 'rgb(12, 15, 9)', panel: 'rgb(8, 10, 6)', task: 'rgb(33, 40, 24)', run: 'rgb(144, 169, 110)', runInk: 'rgb(16, 20, 12)', metadata: 'rgb(198, 210, 180)', inputBorder: 'rgb(114, 132, 94)' });
  await page.getByRole('button', { name: 'Motion lab', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCSS('background-color', 'rgb(8, 10, 6)');
  expect(await page.getByRole('dialog').evaluate(element => getComputedStyle(element, '::backdrop').backgroundColor)).toBe('rgba(8, 10, 6, 0.79)');
});

test('Expressive toolbar control baselines and canvas actions align at supported widths', async ({ page }) => {
  for (const width of [1100, 1280, 1600, 2512]) {
    await page.setViewportSize({ width, height: 1100 });
    await page.goto('/');
    const geometry = await page.evaluate(() => {
      const rect = (selector: string) => document.querySelector(selector)!.getBoundingClientRect();
      const name = rect('.toolbar-flow-name input');
      const runInput = rect('.run-parameters input');
      const run = rect('.run-actions button');
      const fullscreen = rect('.canvas-header .icon-button');
      const pickerStyle = getComputedStyle(document.querySelector('.flow-picker select')!);
      const controls = [...document.querySelectorAll('.toolbar-group-flow > .button, .flow-picker select')].map(element => element.getBoundingClientRect());
      return { flowBaselineOffsets: controls.filter(control => control.top < name.bottom && control.bottom > name.top).map(control => Math.abs(control.bottom - name.bottom)), runInputGap: run.left - runInput.right, runBaselineOffset: Math.abs(run.bottom - runInput.bottom), runFullscreenOffset: Math.abs(run.right - fullscreen.right), pickerWeight: pickerStyle.fontWeight, runInputSize: getComputedStyle(document.querySelector('.run-parameters input')!).fontSize, overflow: document.documentElement.scrollWidth - innerWidth };
    });
    expect(geometry.flowBaselineOffsets, `flow control baselines at ${width}px`).toEqual(geometry.flowBaselineOffsets.map(() => 0));
    expect(geometry.pickerWeight).toBe('650');
    expect(geometry.runInputSize).toBe('12px');
    expect(geometry.runInputGap, `run parameters remain grouped at ${width}px`).toBeLessThanOrEqual(24);
    expect(geometry.runInputGap).toBeGreaterThanOrEqual(8);
    expect(geometry.runBaselineOffset, `run control baseline at ${width}px`).toBeLessThanOrEqual(1);
    expect(geometry.runFullscreenOffset, `run/fullscreen right edges at ${width}px`).toBeLessThanOrEqual(1);
    expect(geometry.overflow).toBeLessThanOrEqual(0);
  }
});
