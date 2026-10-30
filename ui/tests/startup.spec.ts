import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { createEmptyDraft, importMetadata, STORAGE_KEY } from '../src/model';
import { createDemoDraft } from './fixtures/demo';

const metadata = JSON.parse(await readFile(new URL('./metadata.json', import.meta.url), 'utf8'));
const session = {
  token: 'startup-test', project: metadata.project.root, metadata,
  bindings: Object.fromEntries(metadata.tasks.map((task: { path: string }) => [`local:${task.path}`, 'normalize'])),
  flows: [{ name: 'existing_flow', revision: 'r1', editable: true }],
  environment: { pythonExecutable: '/project/.venv/bin/python', pythonVersion: '3.14.8', weavemVersion: '0.1.0a2' },
};

async function mockSession(page: import('@playwright/test').Page, value = session) {
  await page.route('**/api/session', route => route.fulfill({ json: value }));
}

test('fresh startup discovers real project tasks and flows without opening or running a flow', async ({ page }) => {
  const actions: string[] = [];
  const errors: string[] = [];
  let requests = 0;
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/api/session') requests++;
    if (/\/api\/(flows\/|runs)/.test(request.url())) actions.push(request.url());
  });
  await mockSession(page);
  await page.goto('/');
  await expect(page.getByLabel('Open project flow')).toBeEnabled();
  await expect(page.getByLabel('Open project flow').locator('option')).toContainText(['Open flow…', 'existing_flow']);
  await expect(page.getByTestId('task-node')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: session.project, exact: true })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByText('Choose a flow or create a new one.', { exact: true })).toBeVisible();
  await page.getByText('Project environment', { exact: true }).click();
  await expect(page.getByText('/project/.venv/bin/python', { exact: true })).toBeVisible();
  await expect(page.getByText('Python 3.14.8 · Weavem 0.1.0a2', { exact: true })).toBeVisible();
  await expect(page.getByText(/expressive lab|Motion lab|Sample catalog|prototype/i)).toHaveCount(0);
  expect(actions).toEqual([]);
  expect(errors).toEqual([]);
  expect(requests).toBe(1);
  await page.screenshot({ path: test.info().outputPath('connected-project.png'), fullPage: true });
});

test('empty real project provides honest new-flow guidance', async ({ page }) => {
  const empty = structuredClone(session);
  empty.metadata.tasks = []; empty.metadata.releases = []; empty.metadata.bindings = [];
  empty.bindings = {}; empty.flows = [];
  await mockSession(page, empty);
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'New flow', exact: true })).toBeEnabled();
  await expect(page.getByLabel('Open project flow')).toBeDisabled();
  await expect(page.getByText('No tasks are registered in this project.', { exact: true })).toBeVisible();
  await expect(page.getByTestId('task-node')).toHaveCount(0);
});

test('failed connection retains an empty honest workbench and retries without loading a demo', async ({ page }) => {
  let requests = 0;
  await page.route('**/api/session', route => ++requests === 1 ? route.fulfill({ status: 503, json: { error: 'Project temporarily unavailable' } }) : route.fulfill({ json: session }));
  await page.goto('/');
  await expect(page.getByText('Project temporarily unavailable', { exact: true })).toBeVisible();
  await expect(page.getByTestId('task-node')).toHaveCount(0);
  await page.getByRole('button', { name: 'Retry connection', exact: true }).click();
  await expect(page.getByLabel('Open project flow')).toBeEnabled();
  expect(requests).toBe(2);
});

test('same-project restored work survives automatic connection without opening a saved flow', async ({ page }) => {
  const draft = { ...createEmptyDraft(importMetadata(JSON.stringify(metadata))), name: 'my_unsaved_flow' };
  await page.addInitScript(({ key, value }) => localStorage.setItem(key, value), { key: STORAGE_KEY, value: JSON.stringify(draft) });
  await mockSession(page);
  await page.goto('/');
  await expect(page.getByLabel('Open project flow')).toBeEnabled();
  await expect(page.getByLabel('Flow name', { exact: true })).toHaveValue('my_unsaved_flow');
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

for (const schema of [2, 3]) test(`schema ${schema} legacy browser draft remains recoverable when a different project connects`, async ({ page }) => {
  const draft = { ...createDemoDraft(), schema };
  await page.addInitScript(({ key, value }) => localStorage.setItem(key, value), { key: STORAGE_KEY, value: JSON.stringify(draft) });
  await mockSession(page);
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Refresh project', exact: true })).toBeVisible();
  await expect(page.getByTestId('task-node')).toHaveCount(3);
  await expect(page.getByRole('button', { name: 'Run flow', exact: true })).toBeDisabled();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button', { name: 'Refresh project', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByTestId('task-node')).toHaveCount(3);
  await expect.poll(() => page.evaluate(key => JSON.parse(localStorage.getItem(key)!).schema, STORAGE_KEY)).toBe(3);
  const stored = await page.evaluate(key => JSON.parse(localStorage.getItem(key)!), STORAGE_KEY);
  expect(stored).toMatchObject({ name: draft.name, catalog: draft.catalog, nodes: draft.nodes, edges: draft.edges });
});

test('corrupt storage is never overwritten by an automatic project connection', async ({ page }) => {
  await page.addInitScript(key => localStorage.setItem(key, '{broken'), STORAGE_KEY);
  await mockSession(page);
  await page.goto('/');
  await expect(page.getByText('Autosave paused', { exact: true })).toBeVisible();
  await page.waitForTimeout(450);
  expect(await page.evaluate(key => localStorage.getItem(key), STORAGE_KEY)).toBe('{broken');
  await expect(page.getByTestId('task-node')).toHaveCount(0);
});

test('an edit made during startup prevents automatic draft replacement', async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/session', async route => { await gate; await route.fulfill({ json: session }); });
  await page.goto('/');
  await page.getByLabel('Flow name', { exact: true }).fill('Keep_this_name');
  release();
  await expect(page.getByRole('button', { name: 'Refresh project', exact: true })).toBeVisible();
  await expect(page.getByLabel('Flow name', { exact: true })).toHaveValue('Keep_this_name');
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('an active run requires replacement consent and performs no authenticated request before it', async ({ page }) => {
  const requests: string[] = [];
  await mockSession(page, { ...session, activeRunId: 'already-running' } as typeof session);
  await page.route('**/api/runs/**', route => { requests.push(route.request().url()); return route.fulfill({ json: { runId: 'already-running', status: 'completed', nodes: {}, logs: '' } }); });
  await page.goto('/');
  await expect(page.getByRole('dialog')).toBeVisible();
  expect(requests).toEqual([]);
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  expect(requests).toEqual([]);
});

test('startup has a bounded timeout and keeps runtime unknowns explicitly unavailable', async ({ page }) => {
  await page.clock.install();
  let requested!: () => void;
  const started = new Promise<void>(resolve => { requested = resolve; });
  await page.route('**/api/session', () => { requested(); });
  await page.goto('/');
  await page.clock.runFor(1);
  await started;
  await page.clock.runFor(10_001);
  await expect(page.getByText('The project connection timed out. Check the local editor and retry.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry connection', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Run flow', exact: true })).toBeDisabled();
  const environment = page.locator('.project-environment summary');
  await environment.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByText('Interpreter unavailable', { exact: true })).toBeVisible();
  await expect(page.getByText('Runtime version information unavailable', { exact: true })).toBeVisible();
  await expect(page.getByTestId('task-node')).toHaveCount(0);
});

test('an older startup response cannot overwrite a newer explicit connection', async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let started!: () => void;
  const firstStarted = new Promise<void>(resolve => { started = resolve; });
  const stale = structuredClone(session);
  stale.project = '/stale-project'; stale.metadata.project.root = stale.project;
  let requests = 0;
  await page.route('**/api/session', async route => {
    if (++requests === 1) { started(); await gate; await route.fulfill({ json: stale }); }
    else await route.fulfill({ json: session });
  });
  await page.goto('/');
  await firstStarted;
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  await page.getByRole('button', { name: 'Replace draft', exact: true }).click();
  await expect(page.getByRole('heading', { name: session.project, exact: true })).toBeVisible();
  const staleResponse = page.waitForResponse('**/api/session');
  release();
  await (await staleResponse).finished();
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => resolve())));
  await expect(page.getByText('Connected to /stale-project', { exact: false })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: session.project, exact: true })).toBeVisible();
  expect(requests).toBe(2);
});

test('session body timeout cannot leave startup loading after response headers arrive', async ({ page }) => {
  await page.clock.install();
  await page.addInitScript(() => {
    const fetch = window.fetch.bind(window);
    window.fetch = (input, init) => {
      if (input !== '/api/session') return fetch(input, init);
      const response = new Response('{}', { status: 200 });
      response.json = () => new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
      });
      return Promise.resolve(response);
    };
  });
  await page.goto('/');
  await page.clock.runFor(10_001);
  await expect(page.getByText('The project connection timed out. Check the local editor and retry.', { exact: true })).toBeVisible();
  await expect(page.getByText('Connecting to the local project…', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Retry connection', exact: true })).toBeEnabled();
});
