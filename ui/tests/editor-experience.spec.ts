import { expect, test } from '@playwright/test';

test('undo redo and copying a selected node preserve the authored draft', async ({ page }) => {
  await page.goto('/');
  const nodes = page.getByTestId('task-node');
  await expect(nodes).toHaveCount(3);
  await nodes.first().click();
  await page.getByRole('button', { name: 'Copy selection', exact: true }).click();
  await page.getByRole('button', { name: 'Paste selection', exact: true }).click();
  await expect(nodes).toHaveCount(4);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(nodes).toHaveCount(3);
  await page.getByRole('button', { name: 'Redo', exact: true }).click();
  await expect(nodes).toHaveCount(4);
  await page.getByLabel('Flow name', { exact: true }).fill('Typing is native');
  await page.getByLabel('Flow name', { exact: true }).press('ControlOrMeta+z');
  await expect(nodes).toHaveCount(4);
});

test('toolbar keeps common controls at one height', async ({ page }) => {
  await page.goto('/');
  const heights = await page.locator('.editor-toolbar .button:visible, .editor-toolbar select:visible').evaluateAll((items) => items.map((item) => Math.round(item.getBoundingClientRect().height)));
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(2);
});

test('declared upstream fields produce ordinary key paths and last run stays read-only', async ({ page }) => {
  const { readFile } = await import('node:fs/promises');
  const metadata = JSON.parse(await readFile(new URL('./metadata.json', import.meta.url), 'utf8'));
  const taskKey = `local:${metadata.tasks[0].path}`;
  const graph = { kind: 'weavem.graph', schema: 1, name: 'customer_flow', nodes: [
    { id: 'fetch', taskKey, parameters: {} }, { id: 'send', taskKey, parameters: {} },
  ], edges: [{ id: 'wire', source: 'fetch', target: 'send', argument: 'text' }] };
  await page.route('**/api/session', (route) => route.fulfill({ json: {
    token: 'test', project: metadata.project.root, metadata, bindings: { [taskKey]: 'normalize' },
    flows: [{ name: 'customer_flow', revision: 'r1', editable: true }],
    parameterHints: { [taskKey]: { origin: 'source', parameters: [], output: { kind: 'json', fields: [{ name: 'email', kind: 'string', required: true, hasDefault: false }] } } },
  } }));
  await page.route('**/api/flows/customer_flow', (route) => route.fulfill({ json: { name: 'customer_flow', revision: 'r1', editable: true, graph } }));
  await page.route('**/api/flows/customer_flow/last-run', (route) => route.fulfill({ json: {
    runId: 'past-42', tracking: 'untracked', snapshot: { flowName: 'customer_flow', revision: 'r1', graph, params: { recipient: 'Alice' }, source: 'def customer_flow(): pass' },
    state: { runId: 'past-42', status: 'completed', nodes: {}, logs: '', result: 'sent to Alice' },
  } }));
  await page.goto('/');
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  await page.getByRole('button', { name: 'Replace draft', exact: true }).click();
  await page.getByLabel('Open project flow').selectOption('customer_flow');
  await page.getByRole('button', { name: 'Replace draft', exact: true }).click();
  await page.locator('[data-node-id="send"]').click();
  await page.getByLabel('Upstream field', { exact: true }).selectOption('["email"]');
  await expect(page.getByLabel('Upstream field path')).toHaveValue('["email"]');
  await page.getByLabel('Flow name', { exact: true }).fill('edited_flow');
  await page.getByRole('button', { name: 'Last run', exact: true }).click();
  const past = page.getByRole('region', { name: 'Last run', exact: true });
  await expect(past).toContainText('past-42');
  await expect(past).toContainText('Alice');
  await expect(past.locator('input,textarea')).toHaveCount(0);
  await page.getByRole('button', { name: 'Close last run' }).click();
  await expect(page.getByLabel('Flow name', { exact: true })).toHaveValue('edited_flow');
});

test('deleting several selected nodes is one undoable action', async ({ page }) => {
  await page.goto('/');
  await page.locator('[data-node-id="demo-normalize"]').click();
  await page.locator('[data-node-id="demo-count"]').click({ modifiers: ['ControlOrMeta'] });
  await page.keyboard.press('Delete');
  await expect(page.getByTestId('task-node')).toHaveCount(1);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.getByTestId('task-node')).toHaveCount(3);
  await expect(page.locator('.react-flow__edge')).toHaveCount(2);
});
