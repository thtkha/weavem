import { expect, test, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { createDemoDraft, STORAGE_KEY } from '../src/model';
import type { EditorDraft } from '../src/types';

const metadataFile = new URL('./metadata.json', import.meta.url).pathname;
const node = (page: Page, id: string) => page.locator(`[data-testid="task-node"][data-node-id="${id}"]`);

async function stored(page: Page): Promise<EditorDraft | null> {
  return page.evaluate((key) => {
    const raw = localStorage.getItem(key);
    try { return raw ? JSON.parse(raw) : null; } catch { return null; }
  }, STORAGE_KEY);
}

async function replace(page: Page) {
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Replace draft', exact: true }).click();
  await expect(dialog).not.toBeVisible();
}

async function clear(page: Page) {
  await page.getByRole('button', { name: 'New draft', exact: true }).click();
  await replace(page);
  await expect(page.getByTestId('task-node')).toHaveCount(0);
}

test('demo renders a real canvas with execution safely unavailable', async ({ page }, info) => {
  const errors: string[] = [];
  const external: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => {
    if (request.url().startsWith('http') && new URL(request.url()).hostname !== '127.0.0.1') external.push(request.url());
  });
  await page.goto('/');
  await expect(page.getByTestId('task-node')).toHaveCount(3);
  await expect(page.getByText('Sample catalog', { exact: true })).toBeVisible();
  await expect(page.getByText('Draft wiring · connect a local project to run')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Run flow', exact: true })).toBeDisabled();
  expect((await page.getByRole('region', { name: 'Draft canvas' }).boundingBox())?.height).toBeGreaterThan(400);
  await node(page, 'demo-normalize').click();
  await expect(page.getByLabel('Node label', { exact: true })).toHaveValue('Normalize text');
  await page.screenshot({ path: info.outputPath('workbench.png'), fullPage: true });
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test('connects an explicit project and displays completed run results', async ({ page }) => {
  const snapshot = JSON.parse(await readFile(metadataFile, 'utf-8'));
  let nodeId = '';
  await page.route('**/api/session', async (route) => route.fulfill({ json: {
    token: 'test-token', project: '/projects/document-demo', metadata: snapshot,
    bindings: Object.fromEntries(snapshot.tasks.map((task: { path: string }) => [`local:${task.path}`, 'normalize'])),
  } }));
  await page.route('**/api/runs/run-1', async (route) => route.fulfill({ json: {
    runId: 'run-1', status: 'completed', nodes: { [nodeId]: { status: 'completed', preview: 'done' } }, logs: 'task completed',
  } }));
  await page.route('**/api/runs', async (route) => route.fulfill({ json: { runId: 'run-1', status: 'running' } }));
  await page.goto('/');
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  await replace(page);
  await expect(page.getByText('Project metadata', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Add task text.normalize', exact: true }).first().click();
  nodeId = (await page.getByTestId('task-node').first().getAttribute('data-node-id'))!;
  await expect(page.getByRole('button', { name: 'Run flow', exact: true })).toBeEnabled();
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Run flow', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Run log' })).toContainText('completed');
  await expect(node(page, nodeId)).toContainText('completed');
  await expect(page.getByText('done', { exact: true })).toBeVisible();
  await page.getByLabel('Hide run log', { exact: true }).click();
  await expect(page.getByRole('region', { name: 'Run log' })).toHaveCount(0);
});

test('reconnecting to the same project renews session without replacing the draft', async ({ page }) => {
  const snapshot = JSON.parse(await readFile(metadataFile, 'utf-8'));
  await page.route('**/api/session', async (route) => route.fulfill({ json: {
    token: 'renewed-token', project: '/projects/document-demo', metadata: snapshot,
    bindings: Object.fromEntries(snapshot.tasks.map((task: { path: string }) => [`local:${task.path}`, 'normalize'])),
  } }));
  await page.goto('/');
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  await replace(page);
  await page.getByRole('button', { name: 'Add task text.normalize', exact: true }).first().click();
  await expect(page.getByTestId('task-node')).toHaveCount(1);
  await page.getByRole('button', { name: 'Reconnect project', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByTestId('task-node')).toHaveCount(1);
});

async function connectRunnableProject(page: Page) {
  const snapshot = JSON.parse(await readFile(metadataFile, 'utf-8'));
  await page.route('**/api/session', async (route) => route.fulfill({ json: {
    token: 'test-token', project: '/projects/document-demo', metadata: snapshot,
    bindings: Object.fromEntries(snapshot.tasks.map((task: { path: string }) => [`local:${task.path}`, 'normalize'])),
  } }));
  await page.goto('/');
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  await replace(page);
  await page.getByRole('button', { name: 'Add task text.normalize', exact: true }).first().click();
  page.once('dialog', (dialog) => dialog.accept());
}

test('a failed run reports backend error and skipped work without executing stale parameters', async ({ page }) => {
  let starts = 0; let polls = 0; let nodeIds: string[] = [];
  await page.route('**/api/runs**', async (route) => {
    if (route.request().url().endsWith('/api/runs') && route.request().method() === 'POST') {
      starts += 1; await route.fulfill({ json: { runId: 'run-failed', status: 'running' } }); return;
    }
    if (route.request().url().endsWith('/api/runs/run-failed')) {
      polls += 1;
      await route.fulfill({ json: { runId: 'run-failed', status: 'failed', logs: 'normalize failed\nsummarize skipped', error: 'bad input', nodes: { [nodeIds[0]]: { status: 'failed', error: 'bad input' }, [nodeIds[1]]: { status: 'skipped' } } } }); return;
    }
    await route.fallback();
  });
  await connectRunnableProject(page);
  await page.getByRole('button', { name: 'Add task text.normalize', exact: true }).first().click();
  nodeIds = await page.getByTestId('task-node').evaluateAll((items) => items.map((item) => item.getAttribute('data-node-id')!));
  await page.getByRole('textbox', { name: 'Draft parameters', exact: true }).fill('{"text":"changed but not applied"}');
  await page.getByRole('button', { name: 'Run flow', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Apply the edited parameters');
  expect(starts).toBe(0);
  await page.getByRole('button', { name: 'Apply parameters', exact: true }).click();
  await page.getByRole('button', { name: 'Run flow', exact: true }).click();
  await expect.poll(() => polls).toBeGreaterThan(0);
  await expect(page.getByRole('region', { name: 'Run log' })).toContainText('summarize skipped');
  await expect(page.getByRole('region', { name: 'Run log' })).toContainText('bad input');
  await expect(node(page, nodeIds[0])).toContainText('failed');
  await expect(node(page, nodeIds[1])).toContainText('skipped');
  expect(starts).toBe(1);
});

test('an unmapped wire is blocked before any run request', async ({ page }) => {
  let starts = 0;
  await page.route('**/api/runs', async (route) => { if (route.request().method() !== 'POST') return route.fallback(); starts += 1; await route.fulfill({ json: { runId: 'unexpected', status: 'running' } }); });
  await connectRunnableProject(page);
  await page.getByRole('button', { name: 'Add task text.normalize', exact: true }).first().click();
  const source = page.locator('.react-flow__node').nth(0).locator('.source');
  const target = page.locator('.react-flow__node').nth(1).locator('.target');
  const from = (await source.boundingBox())!;
  const to = (await target.boundingBox())!;
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down(); await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 8 }); await page.mouse.up();
  await page.getByRole('button', { name: 'Run flow', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('target argument');
  expect(starts).toBe(0);
});

test('an active run locks mutation, supports cancellation, and clears results on a later edit', async ({ page }) => {
  let cancelled = false;
  await page.route('**/api/runs', async (route) => { if (route.request().method() !== 'POST') return route.fallback(); await route.fulfill({ json: { runId: 'run-cancel', status: 'running' } }); });
  await page.route('**/api/runs/run-cancel/cancel', async (route) => { cancelled = true; await route.fulfill({ json: {} }); });
  await page.route('**/api/runs/run-cancel', async (route) => route.fulfill({ json: {
    runId: 'run-cancel', status: cancelled ? 'cancelled' : 'running', logs: cancelled ? 'cancelled' : 'running', nodes: {},
  } }));
  await connectRunnableProject(page);
  await page.getByRole('button', { name: 'Run flow', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Cancel run', exact: true })).toBeVisible();
  const cancel = page.getByRole('button', { name: 'Cancel run', exact: true });
  await page.mouse.move(0, 0);
  await expect(cancel).toHaveCSS('background-color', 'rgb(117, 70, 69)');
  await expect(cancel).toHaveCSS('color', 'rgb(237, 241, 231)');
  await expect(cancel.locator('svg')).toHaveCSS('color', 'rgb(237, 241, 231)');
  await cancel.hover();
  await expect(cancel).toHaveCSS('background-color', 'rgb(135, 82, 82)');
  await expect(cancel).toHaveCSS('color', 'rgb(237, 241, 231)');
  await expect(page.getByLabel('Draft name', { exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: /^Add task / }).first()).toBeDisabled();
  await page.getByRole('button', { name: 'Cancel run', exact: true }).click();
  await expect.poll(() => cancelled).toBe(true);
  await expect(page.getByRole('region', { name: 'Run log' })).toContainText('cancelled');
  await page.getByLabel('Node label', { exact: true }).fill('after run');
  await expect(page.getByRole('region', { name: 'Run log' })).toHaveCount(0);
});

test('submission locks the draft before a delayed run request returns', async ({ page }) => {
  let starts = 0;
  let release: (() => void) | undefined;
  const delayed = new Promise<void>((resolve) => { release = resolve; });
  await page.route('**/api/runs', async (route) => {
    starts += 1; await delayed; await route.fulfill({ json: { runId: 'run-delayed', status: 'cancelled' } });
  });
  await connectRunnableProject(page);
  await page.getByRole('button', { name: 'Run flow', exact: true }).click();
  await expect(page.getByLabel('Draft name', { exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Run flow', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Run flow', exact: true }).click({ force: true });
  expect(starts).toBe(1);
  release?.();
  await expect(page.getByLabel('Draft name', { exact: true })).toBeEnabled();
});

test('a bridge error returned while polling is shown verbatim', async ({ page }) => {
  await page.route('**/api/runs', async (route) => { if (route.request().method() !== 'POST') return route.fallback(); await route.fulfill({ json: { runId: 'run-lost', status: 'running' } }); });
  await page.route('**/api/runs/run-lost', async (route) => route.fulfill({ status: 401, json: { error: 'Execution bridge session expired' } }));
  await connectRunnableProject(page);
  await page.getByRole('button', { name: 'Run flow', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Execution bridge session expired');
});

test('search, filters, keyboard add, edits and reload preserve a draft', async ({ page }) => {
  await page.goto('/');
  await clear(page);
  await page.getByRole('button', { name: 'released', exact: true }).click();
  await expect(page.getByRole('button', { name: /^Add task / })).toHaveCount(1);
  await page.getByRole('button', { name: 'All', exact: true }).click();
  await page.getByLabel('Search tasks', { exact: true }).fill('documents.read');
  await page.getByRole('button', { name: 'Add task documents.read', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('task-node')).toHaveCount(1);
  await page.getByLabel('Node label', { exact: true }).fill('Review documents');
  await page.getByRole('textbox', { name: 'Notes', exact: true }).fill('Keep this author note');
  await page.getByRole('textbox', { name: 'Draft parameters', exact: true }).fill('{"paths":["report.md"],"limit":5}');
  await page.getByRole('button', { name: 'Apply parameters', exact: true }).click();
  await page.getByLabel('Draft name', { exact: true }).fill('Quarterly review');
  await expect.poll(async () => (await stored(page))?.nodes[0]?.parameters.limit).toBe(5);
  expect((await stored(page))?.nodes[0]).toMatchObject({ label: 'Review documents', notes: 'Keep this author note' });
  await page.reload();
  await expect(page.getByLabel('Draft name', { exact: true })).toHaveValue('Quarterly review');
  await page.getByTestId('task-node').click();
  await expect(page.getByRole('textbox', { name: 'Notes', exact: true })).toHaveValue('Keep this author note');
  await expect(page.getByRole('textbox', { name: 'Draft parameters', exact: true })).toHaveValue(/report\.md/);
});

test('duplicate task instances have distinct identities and positions', async ({ page }) => {
  await page.goto('/');
  await clear(page);
  const add = page.getByRole('button', { name: 'Add task documents.read', exact: true });
  await add.click();
  await add.click();
  await expect.poll(async () => (await stored(page))?.nodes.length).toBe(2);
  const draft = (await stored(page))!;
  expect(draft.nodes[0].id).not.toBe(draft.nodes[1].id);
  expect(draft.nodes[0].position).not.toEqual(draft.nodes[1].position);
});

test('consecutive library additions use non-overlapping default positions', async ({ page }) => {
  await page.goto('/');
  await clear(page);
  for (const task of ['documents.read', 'text.normalize', 'text.count_words']) {
    await page.getByRole('button', { name: `Add task ${task}`, exact: true }).click();
  }
  await expect.poll(async () => (await stored(page))?.nodes.length).toBe(3);
  const positions = (await stored(page))!.nodes.map((item) => `${item.position.x}:${item.position.y}`);
  expect(new Set(positions).size).toBe(3);
});

test('inspector connects and deletes; invalid parameters do not change saved data', async ({ page }) => {
  await page.goto('/');
  await node(page, 'demo-count').click();
  await page.getByLabel('Add connection target', { exact: true }).selectOption('demo-read');
  await page.getByRole('button', { name: 'Add connection', exact: true }).click();
  await expect.poll(async () => (await stored(page))?.edges.length).toBe(3);
  await page.getByRole('button', { name: 'Delete connection to Read documents', exact: true }).click();
  await expect.poll(async () => (await stored(page))?.edges.length).toBe(2);
  await page.getByRole('textbox', { name: 'Draft parameters', exact: true }).fill('[]');
  await page.getByRole('button', { name: 'Apply parameters', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('JSON object');
  expect((await stored(page))?.nodes.find((item) => item.id === 'demo-count')?.parameters).toEqual({ include_headings: false });
  await page.getByRole('button', { name: 'Delete node', exact: true }).click();
  await expect.poll(async () => (await stored(page))?.edges.length).toBe(1);
  await expect(page.getByTestId('task-node')).toHaveCount(2);
});

test('the inspector reflects existing incoming and outgoing canvas wires', async ({ page }) => {
  await page.goto('/');
  await node(page, 'demo-normalize').click();
  await expect(page.getByRole('heading', { name: 'Incoming connections' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Select connection from Read documents' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Outgoing connections' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Select connection to Count words' })).toBeVisible();
  await page.getByRole('button', { name: 'Select connection to Count words' }).click();
  await expect(page.getByLabel('Connection target argument', { exact: true })).toBeVisible();
});

test('edge endpoints reconnect and preserve a wire on Escape', async ({ page }) => {
  await page.goto('/');
  const targetUpdater = page.locator('.react-flow__edge[data-id="demo-edge-read-normalize"] .react-flow__edgeupdater-target');
  const countTarget = node(page, 'demo-count').locator('.target');
  const from = (await targetUpdater.boundingBox())!;
  const to = (await countTarget.boundingBox())!;
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down(); await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 10 }); await page.mouse.up();
  await expect.poll(async () => (await stored(page))?.edges.find((edge) => edge.id === 'demo-edge-read-normalize')?.target).toBe('demo-count');

  const movedUpdater = page.locator('.react-flow__edge[data-id="demo-edge-read-normalize"] .react-flow__edgeupdater-target');
  const moved = (await movedUpdater.boundingBox())!;
  await page.mouse.move(moved.x + moved.width / 2, moved.y + moved.height / 2); await page.mouse.down(); await page.keyboard.press('Escape'); await page.mouse.up();
  await expect.poll(async () => (await stored(page))?.edges.some((edge) => edge.id === 'demo-edge-read-normalize')).toBe(true);
});

test('releasing an edge endpoint on an empty pane disconnects only that wire', async ({ page }) => {
  await page.goto('/');
  const updater = page.locator('.react-flow__edge[data-id="demo-edge-read-normalize"] .react-flow__edgeupdater-target');
  const endpoint = (await updater.boundingBox())!;
  const pane = (await page.locator('.react-flow__pane').boundingBox())!;
  await page.mouse.move(endpoint.x + endpoint.width / 2, endpoint.y + endpoint.height / 2); await page.mouse.down();
  await page.mouse.move(pane.x + pane.width - 40, pane.y + 90, { steps: 10 }); await page.mouse.up();
  await expect.poll(async () => (await stored(page))?.edges.some((edge) => edge.id === 'demo-edge-read-normalize')).toBe(false);
  expect((await stored(page))?.edges.some((edge) => edge.id === 'demo-edge-normalize-count')).toBe(true);
});

test('pointer connection and node dragging update the independent graph', async ({ page }) => {
  await page.goto('/');
  const source = node(page, 'demo-count').locator('.source');
  const target = node(page, 'demo-read').locator('.target');
  const from = (await source.boundingBox())!;
  const to = (await target.boundingBox())!;
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 18 });
  await page.mouse.up();
  await expect.poll(async () => (await stored(page))?.edges.length).toBe(3);
  const before = (await stored(page))!.nodes.find((item) => item.id === 'demo-normalize')!.position;
  const box = (await node(page, 'demo-normalize').locator('.node-title').boundingBox())!;
  await page.mouse.move(box.x + 30, box.y + 5);
  await page.mouse.down();
  await page.mouse.move(box.x + 75, box.y + 65, { steps: 10 });
  await page.mouse.up();
  await expect.poll(async () => (await stored(page))?.nodes.find((item) => item.id === 'demo-normalize')?.position.y).toBeGreaterThan(before.y + 15);
});

test('library dragging adds a task onto the empty canvas', async ({ page }) => {
  await page.goto('/');
  await clear(page);
  await page.locator('.library-task').filter({ hasText: 'documents.read' }).dragTo(page.locator('.react-flow__pane'));
  await expect(page.getByTestId('task-node')).toHaveCount(1);
});

test('export and reopen preserve neutral data, configuration and viewport', async ({ page }) => {
  await page.goto('/');
  await node(page, 'demo-read').click();
  await page.getByRole('textbox', { name: 'Notes', exact: true }).fill('Portable draft');
  await page.locator('.react-flow__controls-fitview').click();
  await expect.poll(async () => (await stored(page))?.nodes[0].notes).toBe('Portable draft');
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export draft', exact: true }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toMatch(/\.weavem-draft\.json$/);
  const text = await readFile((await download.path())!, 'utf-8');
  const exported = JSON.parse(text) as EditorDraft;
  expect(exported.kind).toBe('weavem.editor-draft');
  expect(exported.nodes[0]).not.toHaveProperty('data');
  await clear(page);
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Open draft', exact: true }).click();
  await (await chooser).setFiles({ name: 'saved.weavem-draft.json', mimeType: 'application/json', buffer: Buffer.from(text) });
  await replace(page);
  await expect(page.getByTestId('task-node')).toHaveCount(3);
  await expect.poll(async () => (await stored(page))?.nodes[0].notes).toBe('Portable draft');
  await expect.poll(async () => (await stored(page))?.viewport.zoom).toBeCloseTo(exported.viewport.zoom, 2);
});

test('real SDK metadata imports tasks, not a reconstructed Python flow', async ({ page }) => {
  await page.goto('/');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Import metadata', exact: true }).click();
  await (await chooser).setFiles(metadataFile);
  await replace(page);
  await expect(page.getByText('Project metadata', { exact: true })).toBeVisible();
  await expect(page.getByTestId('task-node')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Add task text.normalize', exact: true })).toHaveCount(2);
  await page.getByRole('button', { name: 'released', exact: true }).click();
  await page.getByRole('button', { name: 'Add task text.normalize', exact: true }).click();
  await expect(page.getByLabel('Node label', { exact: true })).toHaveValue('text.normalize');
  await expect(page.getByRole('complementary', { name: 'Node inspector' })).toContainText('1.1.0');
});

test('invalid import and cancelled replacement preserve current work', async ({ page }) => {
  await page.goto('/');
  await expect.poll(async () => (await stored(page))?.nodes.length).toBe(3);
  const before = await stored(page);
  await page.getByLabel('Open draft JSON').setInputFiles({ name: 'broken.json', mimeType: 'application/json', buffer: Buffer.from('{') });
  await expect(page.getByRole('alert')).toContainText('not valid JSON');
  expect((await stored(page))?.nodes).toEqual(before?.nodes);
  await page.getByRole('button', { name: 'New draft', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByTestId('task-node')).toHaveCount(3);
});

test('corrupt browser storage is not silently overwritten by demo edits', async ({ page }) => {
  await page.addInitScript((key) => localStorage.setItem(key, '{broken'), STORAGE_KEY);
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Could not load saved draft');
  await page.getByLabel('Draft name', { exact: true }).fill('Recovered visually');
  await page.locator('.react-flow__controls-fitview').click();
  await page.waitForTimeout(600);
  expect(await page.evaluate((key) => localStorage.getItem(key), STORAGE_KEY)).toBe('{broken');
  await clear(page);
  await expect.poll(async () => (await stored(page))?.nodes.length).toBe(0);
});

test('quota failure is visible and still allows export', async ({ page }) => {
  await page.addInitScript(() => {
    Storage.prototype.setItem = () => { throw new DOMException('Quota exceeded', 'QuotaExceededError'); };
  });
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Could not save draft');
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export draft', exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/\.json$/);
});

test('keyboard deletes nodes/edges but not while editing text', async ({ page }) => {
  await page.goto('/');
  const edge = page.locator('.react-flow__edge').first();
  await edge.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Connection target argument', { exact: true })).toBeVisible();
  await page.getByLabel('Connection target argument', { exact: true }).fill('documents');
  await page.getByRole('button', { name: 'Apply mapping', exact: true }).click();
  await edge.focus();
  await page.keyboard.press('Delete');
  await expect.poll(async () => (await stored(page))?.edges.length).toBe(1);
  await node(page, 'demo-normalize').click();
  await page.locator('.react-flow__node[data-id="demo-normalize"]').focus();
  await page.keyboard.press('Delete');
  await expect(page.getByTestId('task-node')).toHaveCount(2);
  await node(page, 'demo-read').click();
  await page.getByLabel('Node label', { exact: true }).focus();
  await page.keyboard.press('Backspace');
  await expect(page.getByTestId('task-node')).toHaveCount(2);
});

test('empty titles are valid and the replacement dialog manages focus', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Draft name', { exact: true }).fill('');
  await expect.poll(async () => (await stored(page))?.name).toBe('');
  await expect(page.getByRole('alert')).toHaveCount(0);
  const start = page.getByRole('button', { name: 'New draft', exact: true });
  await start.click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Replace draft', exact: true }).focus();
  await page.keyboard.press('Tab');
  await expect(dialog.getByRole('button', { name: 'Cancel', exact: true })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(start).toBeFocused();
});

test('small screens retain an export recovery action', async ({ page }) => {
  await page.setViewportSize({ width: 800, height: 700 });
  await page.goto('/');
  await expect(page.getByRole('region', { name: 'Desktop requirement' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Export draft', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Draft canvas' })).not.toBeVisible();
});

test('JSON labels and parameters are never evaluated as code', async ({ page }) => {
  const draft = createDemoDraft();
  draft.nodes[0].label = '<img src=x onerror="window.hacked=true">';
  draft.nodes[0].parameters = { script: 'window.hacked=true' };
  await page.addInitScript(({ key, value }) => localStorage.setItem(key, value), { key: STORAGE_KEY, value: JSON.stringify(draft) });
  await page.goto('/');
  await expect(node(page, 'demo-read')).toContainText('<img src=x');
  expect(await page.evaluate(() => 'hacked' in window)).toBe(false);
});

test('even an empty renamed draft requires confirmation before catalog replacement', async ({ page }) => {
  await page.goto('/');
  await clear(page);
  await page.getByLabel('Draft name', { exact: true }).fill('Keep this empty composition');
  await page.getByLabel('Import metadata JSON').setInputFiles(metadataFile);
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByLabel('Draft name', { exact: true })).toHaveValue('Keep this empty composition');
  await expect(page.getByText('Sample catalog', { exact: true })).toBeVisible();
});

test('unavailable browser storage does not prevent editing or exporting', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', { get: () => { throw new DOMException('Storage denied', 'SecurityError'); } });
  });
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Browser storage is unavailable');
  await expect(page.getByTestId('task-node')).toHaveCount(3);
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export draft', exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/\.json$/);
});

test('includes the run control in draft actions and resizes persistent panels', async ({ page }) => {
  await page.goto('/');
  const run = page.getByRole('button', { name: 'Run flow', exact: true });
  await expect(run).toBeDisabled();
  expect(await run.evaluate((element) => element.parentElement?.classList.contains('run-actions'))).toBe(true);
  await expect(page.locator('.toolbar-actions').getByRole('button', { name: 'Run flow', exact: true })).toHaveCount(1);
  await expect(page.locator('.run-actions')).toHaveCSS('border-left-width', '0px');

  const library = page.getByRole('separator', { name: 'Resize task library' });
  await library.focus();
  await page.keyboard.press('ArrowRight');
  await expect(library).toHaveAttribute('aria-valuenow', '280');
  await page.keyboard.press('End');
  await expect(library).toHaveAttribute('aria-valuenow', '480');
  await page.reload();
  await expect(page.getByRole('separator', { name: 'Resize task library' })).toHaveAttribute('aria-valuenow', '480');
});

test('replaces the header fit control with canvas fullscreen while retaining React Flow controls', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Fit graph in view', exact: true })).toHaveCount(0);
  await expect(page.locator('.react-flow__controls button')).toHaveCount(3);
  const fullscreen = page.getByRole('button', { name: 'Enter canvas fullscreen', exact: true });
  await fullscreen.click();
  await expect(page.getByRole('button', { name: 'Exit canvas fullscreen', exact: true })).toBeVisible();
  expect(await page.locator('.canvas-area').evaluate((element) => document.fullscreenElement === element)).toBe(true);
  await expect(page.locator('.canvas-area').getByRole('button', { name: 'Run flow', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Exit canvas fullscreen', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Enter canvas fullscreen', exact: true })).toBeVisible();
});

test('pointer resizing honors both panel bounds and retains a 430px canvas after a narrow reload', async ({ page }) => {
  await page.goto('/');
  const inspector = page.getByRole('separator', { name: 'Resize inspector' });
  const initial = Number(await inspector.getAttribute('aria-valuenow'));
  const box = (await inspector.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x - 80, box.y + box.height / 2, { steps: 8 });
  await page.mouse.up();
  expect(Number(await inspector.getAttribute('aria-valuenow'))).toBeGreaterThan(initial);
  await inspector.focus();
  await page.keyboard.press('End');
  await expect(inspector).toHaveAttribute('aria-valuenow', '560');

  await page.setViewportSize({ width: 1100, height: 1000 });
  await page.reload();
  const canvas = await page.getByRole('region', { name: 'Draft canvas' }).boundingBox();
  expect(canvas?.width).toBeGreaterThanOrEqual(430);
  expect(Number(await page.getByRole('separator', { name: 'Resize task library' }).getAttribute('aria-valuenow'))).toBeGreaterThanOrEqual(220);
  expect(Number(await page.getByRole('separator', { name: 'Resize inspector' }).getAttribute('aria-valuenow'))).toBeGreaterThanOrEqual(260);
});

test('anchors the unified toolbar to default canvas bounds independently of panel resizing', async ({ page }) => {
  await page.goto('/');
  const run = page.getByRole('button', { name: 'Run flow', exact: true });
  const aligned = async () => {
    await expect.poll(() => page.evaluate(() => {
      const button = document.querySelector('.run-actions button')!.getBoundingClientRect();
      const toolbar = document.querySelector('.toolbar-actions')!.getBoundingClientRect();
      return Math.abs(button.right - (toolbar.right - 16));
    })).toBeLessThanOrEqual(1);
    const button = (await run.boundingBox())!;
    expect(button.x).toBeGreaterThanOrEqual(0);
    for (const action of await page.locator('.toolbar-actions > .button').all()) {
      const other = (await action.boundingBox())!;
      const overlapX = Math.min(button.x + button.width, other.x + other.width) - Math.max(button.x, other.x);
      const overlapY = Math.min(button.y + button.height, other.y + other.height) - Math.max(button.y, other.y);
      expect(overlapX <= 0 || overlapY <= 0).toBe(true);
    }
  };
  const initial = await page.locator('.toolbar-actions').boundingBox();
  const canvas = (await page.locator('.canvas-area').boundingBox())!;
  expect(initial!.x).toBeCloseTo(canvas.x, 0);
  expect(initial!.width).toBeCloseTo(canvas.width, 0);
  await aligned();
  const inspector = page.getByRole('separator', { name: 'Resize inspector' });
  await inspector.focus();
  await page.keyboard.press('End');
  const library = page.getByRole('separator', { name: 'Resize task library' });
  await library.focus();
  await page.keyboard.press('End');
  await aligned();
  expect(await page.locator('.toolbar-actions').boundingBox()).toEqual(initial);
  expect((await page.locator('.canvas-area').boundingBox())!.width).toBeLessThan(canvas.width);
  await page.reload();
  expect(await page.locator('.toolbar-actions').boundingBox()).toEqual(initial);
  await page.setViewportSize({ width: 1100, height: 1000 });
  await aligned();
  await expect(page.getByRole('button', { name: 'Export draft', exact: true })).toBeInViewport();
  await expect(run).toBeInViewport();
  await page.setViewportSize({ width: 2512, height: 1282 });
  await aligned();
  const wide = (await page.locator('.toolbar-actions').boundingBox())!;
  expect(wide.x).toBeCloseTo(280, 0);
  expect(wide.x + wide.width).toBeCloseTo(2512 - 308 - 8, 0);
});

test('task library cards show a hand cursor without changing their add action', async ({ page }) => {
  await page.goto('/');
  const card = page.locator('.library-task').first();
  await card.hover();
  await expect(card).toHaveCSS('cursor', 'pointer');
  await expect(card.locator('code')).toHaveCSS('cursor', 'pointer');
  await expect(card.locator('p').first()).toHaveCSS('cursor', 'pointer');
  const before = await page.getByTestId('task-node').count();
  await card.getByRole('button', { name: /^Add task / }).click();
  await expect(page.getByTestId('task-node')).toHaveCount(before + 1);
});

test('resizers provide the single visible vertical panel boundary', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('complementary', { name: 'Task library', exact: true })).toHaveCSS('border-right-width', '0px');
  await expect(page.getByRole('complementary', { name: 'Node inspector', exact: true })).toHaveCSS('border-left-width', '0px');
  const divider = page.getByRole('separator', { name: 'Resize task library' });
  expect(await divider.evaluate((element) => getComputedStyle(element, '::after').width)).toBe('1px');
  await divider.hover();
  await expect.poll(() => divider.evaluate((element) => getComputedStyle(element, '::after').backgroundColor)).toBe('rgb(144, 169, 110)');
});
