#!/usr/bin/env node
// Real-browser/native-runtime smoke. No wheel build, publication, or mock API.
import { spawn } from 'node:child_process';
import { createWriteStream } from 'node:fs';
import { cp, mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
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
let url;
const project = await mkdtemp(path.join(output, 'project-'));
await cp(path.join(root, 'examples/editor-local'), project, { recursive: true,
  filter: (source) => !source.split(path.sep).includes('.artifacts') });
const python = process.env.WEAVEM_EDITOR_PYTHON || 'python';
const environment = { ...process.env, PYTHONPATH: path.join(root, 'src'),
  WEAVEM_ARTIFACTS_DIR: path.join(output, 'runtime') };
const dialogs = [];
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
    server = spawn(python, [
      '-m', 'weavem', 'editor', '--project', project, '--port', '0',
    ], {
      cwd: root,
      env: environment,
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
  page.on('dialog', (dialog) => { dialogs.push(dialog.message()); void dialog.dismiss(); });
  await page.goto(url);
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  const replace = page.getByRole('button', { name: 'Replace draft', exact: true });
  await replace.click();
  await page.getByLabel('Open project flow', { exact: true }).selectOption('document_summary');
  await replace.click();
  await expect(page.getByTestId('task-node')).toHaveCount(3);
  await expect(page.getByLabel('Flow name', { exact: true })).toHaveValue('document_summary');
  // Save a visually authored copy into normal flows/, not the checked-in example.
  await page.getByRole('button', { name: 'Save as', exact: true }).click();
  await page.getByLabel('New flow name', { exact: true }).fill('visual_summary');
  await page.getByRole('dialog').getByRole('button', { name: 'Save as', exact: true }).click();
  await expect(page.getByLabel('Flow name', { exact: true })).toHaveValue('visual_summary');
  const savedSource = await readFile(path.join(project, 'flows/visual_summary.py'), 'utf8');
  expect(savedSource).toContain('from weavem import flow, task');
  expect(savedSource).not.toContain('editor_worker');
  await page.locator('.react-flow__controls-button').nth(2).click();
  const node = (task) => page.getByTestId('task-node').filter({ hasText: task });
  await page.getByRole('button', { name: 'Run flow', exact: true }).click();
  const log = page.getByRole('region', { name: 'Run log', exact: true });
  await expect(log.getByRole('heading', { name: 'completed', exact: true })).toBeVisible({ timeout: 180_000 });
  for (const task of ['text.normalize', 'text.count_words', 'text.summarize']) {
    await expect(node(task).getByText('completed', { exact: true })).toBeVisible();
  }
  await node('text.summarize').click();
  await expect(page.locator('.run-result')).toContainText('Document: 2 words, 12 characters');
  const preview = page.locator('.run-result pre, .run-result code').first();
  await preview.scrollIntoViewIfNeeded();
  expect(await preview.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const visible = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
    return visible === element || element.contains(visible);
  })).toBe(true);
  const session = await (await page.request.get(`${url}/api/session`)).json();
  const runId = (await log.locator(':scope > code').innerText()).split(' · ')[0];
  const response = await page.request.get(`${url}/api/runs/${runId}`, { headers: { 'X-Weavem-Token': session.token } });
  expect(response.ok()).toBe(true);
  const state = await response.json();
  expect(Object.values(state.nodes).map((entry) => entry.status)).toEqual(['completed', 'completed', 'completed']);
  expect(state.logs).not.toMatch(/Error emitting event|Service 'EventsWorker' failed|Traceback \(most recent call last\)/);
  const inspectionResponse = await page.request.get(`${url}/api/flows/visual_summary/last-run`, { headers: { 'X-Weavem-Token': session.token } });
  expect(inspectionResponse.ok()).toBe(true);
  const inspection = await inspectionResponse.json();
  expect(inspection.runId).toBe(runId);
  expect(inspection.snapshot.source).toBe(savedSource);
  expect(inspection.state.status).toBe('completed');
  expect(inspection.snapshot.graph.nodes).toHaveLength(3);
  expect(pageErrors).toEqual([]);
  expect(dialogs).toEqual([]);
  await page.screenshot({ path: path.join(output, 'completed.png'), fullPage: true });
  await writeFile(path.join(output, 'result.json'), `${JSON.stringify({ url, runId, state, pageErrors }, null, 2)}\n`);
  await page.reload();
  await page.getByRole('button', { name: 'Connect project', exact: true }).click();
  if (await replace.isVisible()) await replace.click();
  await page.getByLabel('Open project flow', { exact: true }).selectOption('visual_summary');
  await replace.click();
  await expect(page.getByTestId('task-node')).toHaveCount(3);
  await expect(page.getByLabel('Flow name', { exact: true })).toHaveValue('visual_summary');
  // Prove a saved source flow is independent of both browser and bridge.
  await browser.close(); browser = undefined; page = undefined;
  await stop();
  const runPython = (args) => new Promise((resolve, reject) => {
    const child = spawn(python, args, { cwd: root, env: environment, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = ''; let stderr = '';
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.on('error', reject);
    const timeout = setTimeout(() => { child.kill('SIGKILL'); reject(new Error('Headless flow timed out')); }, 180_000);
    child.on('close', (code) => { clearTimeout(timeout); code === 0 ? resolve(stdout) : reject(new Error(stderr || stdout)); });
  });
  const cli = await runPython(['-m', 'weavem', '--project', project, 'flow', 'run', 'visual_summary']);
  const expected = { summarize: 'Document: 2 words, 12 characters' };
  expect(JSON.parse(cli.trim().split('\n').at(-1))).toEqual(expected);
  const pythonResult = await runPython(['-c', 'import json,sys; from weavem.flows import load_local_flow; print(json.dumps(load_local_flow("visual_summary", project=sys.argv[1])()))', project]);
  expect(JSON.parse(pythonResult.trim().split('\n').at(-1))).toEqual(expected);
  await writeFile(path.join(output, 'headless.json'), JSON.stringify({ project, result: expected }, null, 2));
  console.log(`PASS: saved native flow ${runId}; GUI, CLI, and Python agree. Evidence: ${output}`);
} catch (error) {
  if (page) await page.screenshot({ path: path.join(output, 'failed.png'), fullPage: true }).catch(() => {});
  throw error;
} finally {
  await stop();
}
