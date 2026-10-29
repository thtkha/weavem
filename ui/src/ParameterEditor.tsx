import { useEffect, useMemo, useState } from 'react';
import type { JsonObject, JsonValue, TaskParameterHints } from './types';
import { parseParameters } from './model';

type Props = {
  value: string;
  onChange: (value: string) => void;
  onApply: () => void;
  disabled: boolean;
  hints?: TaskParameterHints;
  wired: Record<string, string>;
  onPendingChange: (pending: boolean) => void;
};

function stringify(value: JsonObject): string { return JSON.stringify(value, null, 2); }

export function ParameterEditor({ value, onChange, onApply, disabled, hints, wired, onPendingChange }: Props) {
  const [guided, setGuided] = useState(true);
  const [jsonDrafts, setJsonDrafts] = useState<Record<string, string>>({});
  const [jsonErrors, setJsonErrors] = useState<Record<string, string>>({});
  const parsed = useMemo(() => {
    try { return { value: parseParameters(value), error: null as string | null }; }
    catch (error) { return { value: null, error: error instanceof Error ? error.message : String(error) }; }
  }, [value]);
  const fields = hints?.parameters ?? [];
  const update = (name: string, next: JsonValue) => {
    if (!parsed.value) return;
    onChange(stringify({ ...parsed.value, [name]: next }));
  };
  const remove = (name: string) => {
    if (!parsed.value) return;
    const next = { ...parsed.value };
    delete next[name];
    onChange(stringify(next));
  };
  const applyJsonDraft = (name: string, text: string) => {
    if (text === '') {
      remove(name);
      setJsonDrafts((current) => { const next = { ...current }; delete next[name]; return next; });
      setJsonErrors((current) => { const next = { ...current }; delete next[name]; return next; });
      return;
    }
    try {
      update(name, JSON.parse(text) as JsonValue);
      setJsonDrafts((current) => { const next = { ...current }; delete next[name]; return next; });
      setJsonErrors((current) => { const next = { ...current }; delete next[name]; return next; });
    } catch {
      setJsonErrors((current) => ({ ...current, [name]: 'Enter valid JSON before applying parameters.' }));
    }
  };
  const canGuide = fields.length > 0;
  const unresolvedJson = Object.keys(jsonDrafts).length > 0 || Object.keys(jsonErrors).length > 0;
  useEffect(() => { onPendingChange(unresolvedJson); }, [onPendingChange, unresolvedJson]);
  return <section className="parameter-editor" aria-label="Draft parameters">
    {canGuide && <div className="parameter-heading"><button type="button" className="parameter-mode" disabled={disabled || unresolvedJson} onClick={() => setGuided((current) => !current)}>{guided ? 'Edit JSON' : 'Guided fields'}</button></div>}
    {guided && unresolvedJson && <p className="parameter-error" role="alert">Finish or clear the JSON field before switching views or running.</p>}
    {guided && canGuide && parsed.value ? <div className="parameter-fields">
      <p className="field-help">Suggestions from {hints?.origin === 'source' ? 'the local source signature' : 'descriptive metadata'}; runtime remains authoritative.</p>
      {fields.map((field) => {
        const wiredFrom = wired[field.name];
        const current = parsed.value?.[field.name];
        const hasValue = Object.prototype.hasOwnProperty.call(parsed.value, field.name);
        const defaultText = field.defaultDisplay ?? (Object.prototype.hasOwnProperty.call(field, 'defaultValue') ? JSON.stringify(field.defaultValue) : undefined);
        return <div className="parameter-field" key={field.name}>
          <div className="parameter-label"><label htmlFor={`parameter-${field.name}`}>{field.name}{field.annotation ? <small>{field.annotation}</small> : null}</label>{field.required && <em>required</em>}</div>
          {wiredFrom ? <p className="parameter-wired">Connected from <strong>{wiredFrom}</strong></p> : field.kind === 'boolean' ? <select id={`parameter-${field.name}`} disabled={disabled} value={!hasValue ? '__default__' : current === true ? 'true' : current === false ? 'false' : 'invalid'} onChange={(event) => { if (event.target.value === '__default__') remove(field.name); else if (event.target.value === 'true') update(field.name, true); else if (event.target.value === 'false') update(field.name, false); }}><option value="__default__">{field.hasDefault ? 'Use default' : 'Unset'}</option><option value="true">True</option><option value="false">False</option>{current !== true && current !== false && hasValue && <option value="invalid">Use JSON editor</option>}</select> : field.kind === 'number' ? <><input id={`parameter-${field.name}`} type="number" disabled={disabled} value={typeof current === 'number' ? current : ''} placeholder={defaultText} onChange={(event) => event.target.value === '' ? remove(field.name) : update(field.name, Number(event.target.value))} /><button type="button" className="parameter-unset" disabled={disabled || !hasValue} onClick={() => remove(field.name)}>{field.hasDefault ? 'Use default' : 'Unset'}</button></> : field.kind === 'string' ? <><input id={`parameter-${field.name}`} type="text" disabled={disabled} value={typeof current === 'string' ? current : ''} placeholder={defaultText} onChange={(event) => update(field.name, event.target.value)} /><button type="button" className="parameter-unset" disabled={disabled || !hasValue} onClick={() => remove(field.name)}>{field.hasDefault ? 'Use default' : 'Unset'}</button></> : <><textarea id={`parameter-${field.name}`} className="code-area parameter-json" disabled={disabled} value={jsonDrafts[field.name] ?? (hasValue ? JSON.stringify(current) : '')} placeholder={defaultText ?? 'JSON value'} onChange={(event) => { setJsonDrafts((drafts) => ({ ...drafts, [field.name]: event.target.value })); }} onBlur={(event) => applyJsonDraft(field.name, event.target.value)} />{jsonErrors[field.name] && <small className="parameter-error" role="alert">{jsonErrors[field.name]}</small>}<button type="button" className="parameter-unset" disabled={disabled || !hasValue} onClick={() => { remove(field.name); setJsonDrafts((drafts) => { const next = { ...drafts }; delete next[field.name]; return next; }); setJsonErrors((errors) => { const next = { ...errors }; delete next[field.name]; return next; }); }}>{field.hasDefault ? 'Use default' : 'Unset'}</button></>}
          {!wiredFrom && !hasValue && defaultText && <small className="parameter-default">Default: {defaultText}</small>}
        </div>;
      })}
    </div> : <><textarea className="code-area" aria-label="Draft parameters" value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} spellCheck={false} aria-describedby="parameter-help" />{parsed.error && <p className="parameter-error" role="alert">{parsed.error}</p>}<p id="parameter-help" className="field-help">JSON object saved only in this editor draft. Unknown keys are retained.</p></>}
    <button className="button secondary wide" disabled={disabled || Boolean(parsed.error) || unresolvedJson} onClick={onApply}>Apply parameters</button>
  </section>;
}
