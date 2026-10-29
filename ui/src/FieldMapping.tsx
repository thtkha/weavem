import { useState } from 'react';
import type { JsonValue, ParameterHint, ValuePreview } from './types';
import { Button } from './components/Button';

type Path = Array<string | number>;
export function observedPaths(value: JsonValue, path: Path = [], depth = 0): Path[] {
  if (depth >= 6 || value === null || typeof value !== 'object') return [];
  return Object.entries(value).slice(0, 100).flatMap(([key, child]) => {
    const next = [...path, Array.isArray(value) ? Number(key) : key];
    return [next, ...observedPaths(child, next, depth + 1)];
  }).slice(0, 100);
}
function declaredPaths(fields: ParameterHint[], path: Path = [], depth = 0): Path[] {
  if (depth >= 6) return [];
  return fields.flatMap((field) => { const next = [...path, field.name]; return [next, ...declaredPaths(field.fields ?? [], next, depth + 1)]; }).slice(0, 100);
}
export function FieldMapping({ path, fields = [], observed, runId, disabled, onApply }: {
  path?: Path; fields?: ParameterHint[]; observed?: ValuePreview; runId?: string; disabled: boolean; onApply: (path: Path) => void;
}) {
  const [text, setText] = useState(JSON.stringify(path ?? []));
  const [error, setError] = useState('');
  const apply = () => {
    try {
      const parsed: unknown = JSON.parse(text);
      if (!Array.isArray(parsed) || parsed.length > 32 || parsed.some((part) => typeof part !== 'string' && !(typeof part === 'number' && Number.isSafeInteger(part) && part >= 0))) throw new Error('Use an array of string keys or non-negative integer indexes.');
      onApply(parsed as Path); setError('');
    } catch (cause) { setError(String(cause)); }
  };
  return <section aria-label="Upstream field mapping">
    <label>Upstream value<select aria-label="Upstream field" disabled={disabled} value="" onChange={(event) => { if (event.target.value) { const next = JSON.parse(event.target.value) as Path; setText(JSON.stringify(next)); onApply(next); } }}>
      <option value="">Choose a field or use the whole result</option><option value="[]">Whole result</option>
      {declaredPaths(fields).map((item) => <option key={`d:${JSON.stringify(item)}`} value={JSON.stringify(item)}>Declared: {JSON.stringify(item)}</option>)}
      {observed?.kind === 'json' && !observed.truncated && observed.value !== undefined && observedPaths(observed.value).map((item) => <option key={`o:${JSON.stringify(item)}`} value={JSON.stringify(item)}>Observed: {JSON.stringify(item)}</option>)}
    </select></label>
    {observed && <p className="field-help">Observed in run {runId}; example data, not a guarantee.{observed.truncated ? ' Sample truncated; observed field suggestions are unavailable.' : ''}</p>}
    {!fields.length && !observed && <p className="field-help">Output fields unknown. Supply a path manually or run explicitly for a sample.</p>}
    <label>Field path (JSON)<input aria-label="Upstream field path" disabled={disabled} value={text} onChange={(event) => setText(event.target.value)} placeholder={'["customer", "email"]'} /></label>
    <p className="field-help">[] passes the whole result. String keys and non-negative list indexes only.</p>
    <Button disabled={disabled} onClick={apply}>Apply field path</Button>{error && <p role="alert">{error}</p>}
  </section>;
}
