import { useState } from 'react';
import type { JsonObject, JsonValue, ValuePreview } from './types';

type Props = { value?: ValuePreview; fallback?: string };

function isObject(value: JsonValue): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function Tree({ value }: { value: JsonValue }) {
  if (Array.isArray(value)) return <details open><summary>List ({value.length})</summary><ol className="result-tree">{value.map((item, index) => <li key={index}><Tree value={item} /></li>)}</ol></details>;
  if (isObject(value)) return <details open><summary>Object ({Object.keys(value).length} fields)</summary><dl className="result-tree">{Object.entries(value).map(([key, item]) => <div key={key}><dt>{key}</dt><dd><Tree value={item} /></dd></div>)}</dl></details>;
  return <code>{JSON.stringify(value)}</code>;
}

function Table({ rows }: { rows: JsonObject[] }) {
  const keys = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  return <table className="result-table"><thead><tr>{keys.map((key) => <th key={key}>{key}</th>)}</tr></thead><tbody>
    {rows.map((row, index) => <tr key={index}>{keys.map((key) => <td key={key}><Tree value={row[key] ?? null} /></td>)}</tr>)}
  </tbody></table>;
}

/** Displays only the bounded, server-provided result envelope. */
export function ResultViewer({ value, fallback }: Props) {
  const [table, setTable] = useState(false);
  if (!value) return fallback ? <pre className="result-viewer">{fallback}</pre> : null;
  if (value.kind === 'json' && value.value !== undefined) {
    const rows = Array.isArray(value.value) && value.value.every(isObject) ? value.value : null;
    return <section className="result-viewer" aria-label="Structured result">{rows && <button type="button" onClick={() => setTable((current) => !current)}>{table ? "Tree view" : "Table view"}</button>}{rows && table ? <Table rows={rows} /> : <Tree value={value.value} />}{value.truncated && <small>Preview truncated.</small>}</section>;
  }
  return <pre className="result-viewer">{value.preview}{value.truncated ? '\\n[truncated]' : ''}</pre>;
}
