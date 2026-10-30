import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { ResultTable } from './ResultViewer';

it('distinguishes missing record fields from explicit null', () => {
  const html = renderToStaticMarkup(createElement(ResultTable, { rows: [{ a: null }, { b: 1 }] }));
  expect(html).toContain('Missing field');
  expect(html).toContain('<code>null</code>');
  expect(html.match(/Missing field/g)).toHaveLength(2);
});
