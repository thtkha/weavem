import { expect, test, type Page } from './fixtures';
import { readFile } from 'node:fs/promises';
import { STORAGE_KEY } from '../src/model';
import type { EditorDraft } from '../src/types';

const metadataFile = new URL('./metadata.json', import.meta.url).pathname;

async function replace(page: Page) {
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Replace draft', exact: true }).click();
  await expect(dialog).not.toBeVisible();
}

async function stored(page: Page): Promise<EditorDraft | null> {
  return page.evaluate((key) => {
    const raw = localStorage.getItem(key);
    try { return raw ? JSON.parse(raw) : null; } catch { return null; }
  }, STORAGE_KEY);
}

test('guided number fields preserve zero and expose default and required context', async ({ page }) => {
  const snapshot = JSON.parse(await readFile(metadataFile, 'utf-8'));
  const release = snapshot.releases[0];
  const taskKey = `released:${release.root}:${release.manifest_sha256}`;
  await page.route('**/api/session', async (route) => route.fulfill({ json: {
    token: 'test-token', project: '/projects/document-demo', metadata: snapshot,
    bindings: { [taskKey]: 'normalize' },
    parameterHints: { [taskKey]: { origin: 'metadata', parameters: [
      { name: 'limit', kind: 'number', required: true, hasDefault: true, defaultValue: 3 },
    ] } },
  } }));

  await page.goto('/');
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  await replace(page);
  await page.getByRole('button', { name: 'Add task text.normalize', exact: true }).last().click();
  await page.getByTestId('task-node').click();

  const parameters = page.getByRole('region', { name: 'Draft parameters', exact: true });
  const limit = parameters.getByLabel('limit', { exact: true });
  await expect(parameters.locator('.parameter-label')).toContainText('limitrequired');
  await expect(parameters.getByText('Default: 3', { exact: true })).toBeVisible();
  await expect(limit).toHaveValue('');
  await limit.fill('0');
  await expect(limit).toHaveValue('0');
  await page.getByRole('button', { name: 'Apply parameters', exact: true }).click();
  await expect.poll(async () => (await stored(page))?.nodes[0]?.parameters).toEqual({ limit: 0 });

  await parameters.getByRole('button', { name: 'Use default', exact: true }).click();
  await expect(limit).toHaveValue('');
  await expect(parameters.getByText('Default: 3', { exact: true })).toBeVisible();
});
