import type { JsonObject, JsonValue, ValuePreview } from './types';

type Props = { value?: ValuePreview; fallback?: string };

function isObject(value: JsonValue): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function Tree({ value }: { value: JsonValue }) {
  if (Array.isArray(value)) return <ol className="result-tree">{value.map((item, index) => <li key={index}><Tree value={item} /></li>)}</ol>;
  if (isObject(value)) return <dl className="result-tree">{Object.entries(value).map(([key, item]) => <div key={key}><dt>{key}</dt><dd><Tree value={item} /></dd></div>)}</dl>;
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
  if (!value) return fallback ? <pre className="run-result">{fallback}</pre> : null;
  if (value.kind === 'json' && value.value !== undefined) {
    const rows = Array.isArray(value.value) && value.value.every(isObject) ? value.value : null;
    return <section className="run-result" aria-label="Run result">{rows ? <Table rows={rows} /> : <Tree value={value.value} />}{value.truncated && <small>Preview truncated.</small>}</section>;
  }
  return <pre className="run-result">{value.preview}{value.truncated ? '\\n[truncated]' : ''}</pre>;
}
