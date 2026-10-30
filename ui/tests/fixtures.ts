import { test as base } from '@playwright/test';
import { createDemoDraft } from './fixtures/demo';
import { STORAGE_KEY } from '../src/model';

/** Explicit legacy draft fixture; normal application startup never loads sample data. */
export const test = base.extend({
  page: async ({ page }, use) => {
    await page.addInitScript(({ key, draft }) => {
      try { if (localStorage.getItem(key) === null) localStorage.setItem(key, draft); } catch { /* Storage failure tests own recovery assertions. */ }
      const fetch = window.fetch.bind(window);
      let bootstrap = true;
      window.fetch = (input, init) => {
        const path = typeof input === 'string' ? input : input instanceof URL ? input.pathname : input.url;
        if (bootstrap && path === '/api/session') {
          bootstrap = false;
          return Promise.resolve(new Response(JSON.stringify({ error: 'Fixture starts disconnected' }), { status: 503, headers: { 'Content-Type': 'application/json' } }));
        }
        return fetch(input, init);
      };
    }, { key: STORAGE_KEY, draft: JSON.stringify(createDemoDraft()) });
    await use(page);
  },
});
export { expect } from '@playwright/test';
export type { Page, Locator } from '@playwright/test';
