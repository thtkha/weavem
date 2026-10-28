#!/usr/bin/env node
// Real-browser/native-runtime smoke. No wheel build, publication, or mock API.
import { spawn } from 'node:child_process';
import { createWriteStream } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';

const root = fileURLToPath(new URL('../', import.meta.url));
const require = createRequire(new URL('../ui/package.json', import.meta.url));
const { chromium, expect } = require('@playwright/test');
const output = path.resolve(process.env.WEAVEM_EDITOR_EVIDENCE || path.join(root, '.artifacts/node-editor/live'));
await mkdir(output, { recursive: true });
const serverLog = createWriteStream(path.join(output, 'server.log'));
let server;
let browser;
let page;
let serverOutput = '';
let url = process.env.WEAVEM_EDITOR_URL;
const pageErrors = [];

async function stop() {
  if (browser) await browser.close();
  if (server && server.exitCode === null) {
    server.kill('SIGINT');
    for (let attempt = 0; attempt < 50 && server.exitCode === null; attempt++) await delay(100);
    if (server.exitCode === null) server.kill('SIGKILL');
  }
  serverLog.end();
}

try {
  if (!url) {
    server = spawn(process.env.WEAVEM_EDITOR_PYTHON || 'python', [
      '-m', 'weavem', 'editor', '--project', 'examples/editor-local', '--port', '0',
    ], {
      cwd: root,
      env: {
        ...process.env,
        PYTHONPATH: path.join(root, 'src'),
        WEAVEM_ARTIFACTS_DIR: path.join(output, 'runtime'),
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    server.on('error', (error) => { serverOutput += String(error); });
    for (const stream of [server.stdout, server.stderr]) stream.on('data', (chunk) => {
      serverOutput += chunk.toString(); serverLog.write(chunk);
    });
    for (let attempt = 0; attempt < 100; attempt++) {
      url = serverOutput.match(/Weavem editor: (http:\/\/127\.0\.0\.1:\d+)/)?.[1];
      if (url) break;
      if (server.exitCode !== null) throw new Error(`Editor failed to start: ${serverOutput}`);
      await delay(100);
    }
    if (!url) throw new Error(`No editor URL after 10 seconds: ${serverOutput}`);
  }
  browser = await chromium.launch({ headless: true });
  page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('dialog', (dialog) => dialog.accept());
  await page.goto(url);
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  await page.getByRole('button', { name: 'Replace draft', exact: true }).click();
  // Match the user's quick-start: connect, accept the saved flow, then Run.
  // No node creation, parameter edits, or wire mapping is needed.
  await expect(page.getByTestId('task-node')).toHaveCount(3);
  await expect(page.getByLabel('Draft name', { exact: true })).toHaveValue('Native document summary');
  await page.getByRole('button', { name: 'Fit graph in view', exact: true }).click();
  const node = (task) => page.getByTestId('task-node').filter({ hasText: task });
  await page.getByRole('button', { name: 'Run flow', exact: true }).click();
  const log = page.getByRole('region', { name: 'Run log', exact: true });
  await expect(log.getByRole('heading', { name: 'completed', exact: true })).toBeVisible({ timeout: 180_000 });
  for (const task of ['text.normalize', 'text.count_words', 'text.summarize']) {
    await expect(node(task).getByText('completed', { exact: true })).toBeVisible();
  }
  await node('text.summarize').click();
  await expect(page.locator('.run-result')).toContainText('Document: 2 words, 12 characters');
  const preview = page.locator('.run-result pre');
  await preview.scrollIntoViewIfNeeded();
  expect(await preview.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const visible = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
    return visible === element || element.contains(visible);
  })).toBe(true);
  const session = await (await page.request.get(`${url}/api/session`)).json();
  const runId = await log.locator('code').innerText();
  const response = await page.request.get(`${url}/api/runs/${runId}`, { headers: { 'X-Weavem-Token': session.token } });
  const state = await response.json();
  expect(Object.values(state.nodes).map((entry) => entry.status)).toEqual(['completed', 'completed', 'completed']);
  expect(state.logs).not.toMatch(/Error emitting event|Service 'EventsWorker' failed|Traceback \(most recent call last\)/);
  expect(pageErrors).toEqual([]);
  await page.screenshot({ path: path.join(output, 'completed.png'), fullPage: true });
  await writeFile(path.join(output, 'result.json'), `${JSON.stringify({ url, runId, state, pageErrors }, null, 2)}\n`);
  console.log(`PASS: real native canvas flow completed (${runId}). Evidence: ${output}`);
} catch (error) {
  if (page) await page.screenshot({ path: path.join(output, 'failed.png'), fullPage: true }).catch(() => {});
  throw error;
} finally {
  await stop();
}
