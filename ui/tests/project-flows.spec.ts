import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';

const metadataFile = new URL('./metadata.json', import.meta.url).pathname;

async function projectSession() {
  const metadata = JSON.parse(await readFile(metadataFile, 'utf-8'));
  return {
    token: 'test-token', project: '/projects/document-demo', metadata,
    bindings: Object.fromEntries(metadata.tasks.map((task: { path: string }) => [`local:${task.path}`, 'normalize'])),
    flows: [],
  };
}

test('saves an ordinary project flow before running it, without a native confirmation popup', async ({ page }) => {
  const session = await projectSession();
  const saves: unknown[] = [];
  let postedRun: unknown;
  await page.route('**/api/session', (route) => route.fulfill({ json: session }));
  await page.route('**/api/flows/visual_flow', async (route) => {
    saves.push(route.request().postDataJSON());
    await route.fulfill({ json: { name: 'visual_flow', revision: 'r1', editable: true } });
  });
  await page.route('**/api/runs', async (route) => {
    postedRun = route.request().postDataJSON();
    await route.fulfill({ json: { runId: 'run-visual', status: 'completed', flowName: 'visual_flow', revision: 'r1' } });
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Replace draft', exact: true }).click();
  await page.getByRole('button', { name: 'Add task text.normalize', exact: true }).first().click();
  await page.getByLabel('Flow name', { exact: true }).fill('visual_flow');
  await page.getByRole('button', { name: 'Run flow', exact: true }).click();

  await expect.poll(() => saves.length).toBe(1);
  expect(saves[0]).toMatchObject({
    expectedRevision: null,
    graph: { kind: 'weavem.graph', schema: 1, name: 'visual_flow', nodes: [{ taskKey: expect.any(String) }] },
    layout: { schema: 1, nodes: [{ position: expect.any(Object) }] },
  });
  await expect.poll(() => postedRun).toEqual({ flowName: 'visual_flow', revision: 'r1', params: {} });
});

test('opens source-only flows as runnable but not visually rewritable', async ({ page }) => {
  const session = { ...await projectSession(), flows: [{ name: 'handwritten', revision: 'r7', editable: false, reason: 'contains a Python conditional' }] };
  let postedRun: unknown;
  await page.route('**/api/session', (route) => route.fulfill({ json: session }));
  await page.route('**/api/flows/handwritten', (route) => route.fulfill({ json: {
    name: 'handwritten', revision: 'r7', editable: false, reason: 'contains a Python conditional', graph: null, source: 'def handwritten(value): ...',
  } }));
  await page.route('**/api/runs', async (route) => {
    postedRun = route.request().postDataJSON();
    await route.fulfill({ json: { runId: 'run-source', status: 'completed' } });
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Replace draft', exact: true }).click();
  await page.getByLabel('Open project flow', { exact: true }).selectOption('handwritten');
  await page.getByRole('dialog').getByRole('button', { name: 'Replace draft', exact: true }).click();
  await expect(page.locator('.source-only-notice')).toContainText('contains a Python conditional');
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled();
  await page.getByLabel('Run parameters JSON', { exact: true }).fill('{"value":"hello"}');
  await page.getByRole('button', { name: 'Run flow', exact: true }).click();
  await expect.poll(() => postedRun).toEqual({ flowName: 'handwritten', revision: 'r7', params: { value: 'hello' } });
});

test('a delayed manual save locks editing and does not permit a concurrent save', async ({ page }) => {
  const session = await projectSession();
  let saves = 0;
  let release: (() => void) | undefined;
  const delayed = new Promise<void>((resolve) => { release = resolve; });
  await page.route('**/api/session', (route) => route.fulfill({ json: session }));
  await page.route('**/api/flows/new_flow', async (route) => {
    saves += 1;
    await delayed;
    await route.fulfill({ json: { name: 'new_flow', revision: 'r1', editable: true } });
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Replace draft', exact: true }).click();
  await page.getByRole('button', { name: 'Add task text.normalize', exact: true }).first().click();
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByLabel('Flow name', { exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Save', exact: true }).click({ force: true });
  expect(saves).toBe(1);
  release?.();
  await expect(page.getByLabel('Flow name', { exact: true })).toBeEnabled();
  expect(saves).toBe(1);
});

test('Save as updates the visible flow name only after the new flow is saved', async ({ page }) => {
  const session = await projectSession();
  await page.route('**/api/session', (route) => route.fulfill({ json: session }));
  await page.route('**/api/flows/renamed_flow', (route) => route.fulfill({ json: { name: 'renamed_flow', revision: 'r2', editable: true } }));
  await page.goto('/');
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Replace draft', exact: true }).click();
  await page.getByRole('button', { name: 'Add task text.normalize', exact: true }).first().click();
  await page.getByRole('button', { name: 'Save as', exact: true }).click();
  await page.getByLabel('New flow name', { exact: true }).fill('renamed_flow');
  await page.getByRole('dialog').getByRole('button', { name: 'Save as', exact: true }).click();
  await expect(page.getByLabel('Flow name', { exact: true })).toHaveValue('renamed_flow');
  await expect(page.getByText('Saved flow renamed_flow', { exact: true })).toBeVisible();
});

test('active-run attachment waits for replacement confirmation', async ({ page }) => {
  const session = {
    ...await projectSession(), activeRunId: 'active-1',
    flows: [{ name: 'running_flow', revision: 'r1', editable: true }],
  };
  let runFetches = 0;
  await page.route('**/api/session', (route) => route.fulfill({ json: session }));
  await page.route('**/api/runs/active-1', (route) => {
    runFetches += 1;
    return route.fulfill({ json: { runId: 'active-1', status: 'running', flowName: 'running_flow', revision: 'r1', nodes: {}, logs: '' } });
  });
  await page.route('**/api/flows/running_flow', (route) => route.fulfill({ json: {
    name: 'running_flow', revision: 'r1', editable: true,
    graph: { kind: 'weavem.graph', schema: 1, name: 'running_flow', nodes: [], edges: [] },
  } }));
  await page.goto('/');
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByText('Synthetic document pipeline', { exact: true })).toBeVisible();
  expect(runFetches).toBe(0);
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Replace draft', exact: true }).click();
  await expect.poll(() => runFetches).toBeGreaterThan(0);
  await expect(page.getByRole('region', { name: 'Run log', exact: true })).toContainText('active-1');
});

test('Save as traps focus, reports validation inside the dialog and restores focus', async ({ page }) => {
  const session = await projectSession();
  await page.route('**/api/session', route => route.fulfill({ json: session }));
  await page.goto('/');
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  await page.getByRole('button', { name: 'Replace draft', exact: true }).click();
  await page.getByRole('button', { name: 'Add task text.normalize', exact: true }).first().click();
  const trigger = page.getByRole('button', { name: 'Save as', exact: true });
  await trigger.click();
  const modal = page.getByRole('dialog');
  await modal.getByLabel('New flow name').fill('not valid!');
  await modal.getByRole('button', { name: 'Save as', exact: true }).click();
  await expect(modal.getByRole('alert')).toContainText('Flow name');
  await modal.getByRole('button', { name: 'Save as', exact: true }).focus();
  await page.keyboard.press('Tab');
  await expect(modal.getByLabel('New flow name')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(modal).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await expect(page.locator('input[type=file]').first()).toHaveAttribute('tabindex', '-1');
});

test('run polling waits for the previous response and stops after completion', async ({ page }) => {
  const session = { ...await projectSession(), activeRunId: 'serial-run', flows: [{ name: 'running_flow', revision: 'r1', editable: true }] };
  let requests = 0;
  let release: () => void = () => {};
  const delayed = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/session', route => route.fulfill({ json: session }));
  await page.route('**/api/flows/running_flow', route => route.fulfill({ json: { name: 'running_flow', revision: 'r1', editable: true, graph: { kind: 'weavem.graph', schema: 1, name: 'running_flow', nodes: [], edges: [] } } }));
  await page.route('**/api/runs/serial-run', async route => {
    requests += 1;
    const number = requests;
    if (number === 2) await delayed;
    await route.fulfill({ json: { runId: 'serial-run', status: number >= 3 ? 'completed' : 'running', flowName: 'running_flow', revision: 'r1', nodes: {}, logs: '' } });
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  await page.getByRole('button', { name: 'Replace draft', exact: true }).click();
  await expect.poll(() => requests).toBe(2);
  await page.waitForTimeout(700);
  expect(requests).toBe(2);
  release();
  await expect(page.getByRole('region', { name: 'Run log', exact: true }).getByRole('heading')).toHaveText('completed');
  await page.waitForTimeout(700);
  expect(requests).toBe(3);
});

test('Save as cannot be dismissed while its pending save can still fail', async ({ page }) => {
  const session = await projectSession();
  await page.route('**/api/session', route => route.fulfill({ json: session }));
  let submitted = false;
  let release: () => void = () => {};
  const delayed = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/flows/delayed_copy', async route => {
    submitted = true;
    await delayed;
    await route.fulfill({ status: 500, json: { error: 'Simulated save failure' } });
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  await page.getByRole('button', { name: 'Replace draft', exact: true }).click();
  await page.getByRole('button', { name: 'Add task text.normalize', exact: true }).first().click();
  await page.getByRole('button', { name: 'Save as', exact: true }).click();
  const modal = page.getByRole('dialog');
  await modal.getByLabel('New flow name').fill('delayed_copy');
  await modal.getByRole('button', { name: 'Save as', exact: true }).click();
  await expect.poll(() => submitted).toBe(true);
  await page.waitForTimeout(550);
  await page.keyboard.press('Escape');
  await expect(modal).toBeVisible();
  await expect(modal.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  release();
  await expect(modal.getByRole('alert')).toContainText('Simulated save failure');
  await page.keyboard.press('Escape');
  await expect(modal).toHaveCount(0);
});

test('toolbar and inspector field boundaries retain at least 3:1 contrast', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('task-node').first().click();
  const checks = await page.locator('input:visible, textarea:visible, select:visible').evaluateAll(elements => {
    const luminance = (color: string) => {
      const channels = color.match(/[\d.]+/g)!.slice(0, 3).map(Number).map(n => { const s = n / 255; return s <= .04045 ? s / 12.92 : ((s + .055) / 1.055) ** 2.4; });
      return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2];
    };
    return elements.map(element => {
      const style = getComputedStyle(element);
      const border = luminance(style.borderTopColor);
      const background = luminance(style.backgroundColor);
      return { name: element.getAttribute('aria-label') ?? element.tagName, ratio: (Math.max(border, background) + .05) / (Math.min(border, background) + .05) };
    });
  });
  expect(checks.length).toBeGreaterThan(2);
  for (const check of checks) expect(check.ratio, check.name).toBeGreaterThanOrEqual(3);
});

test('raw parameter JSON uses the editor theme instead of browser white', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('task-node').first().click();
  const textarea = page.locator('textarea[aria-label="Draft parameters"]');
  await expect(textarea).toBeVisible();
  const theme = await textarea.evaluate(element => {
    const style = getComputedStyle(element);
    return { background: style.backgroundColor, ink: style.color, placeholder: getComputedStyle(element, '::placeholder').color };
  });
  expect(theme).toEqual({ background: 'rgb(8, 10, 6)', ink: 'rgb(237, 241, 231)', placeholder: 'rgb(198, 210, 180)' });
});
