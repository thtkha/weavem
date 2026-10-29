import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Button } from './components/Button';
import { parseParameters } from './model';
import type { JsonObject, JsonValue, ParameterHint, TaskParameterHints } from './types';

type Props = {
  value: string;
  onChange: (value: string) => void;
  onApply: () => void;
  disabled: boolean;
  hints?: TaskParameterHints;
  wired: Record<string, string>;
  onPendingChange: (pending: boolean) => void;
};

type ParameterFieldProps = {
  field: ParameterHint;
  current: JsonValue | undefined;
  hasValue: boolean;
  wiredFrom?: string;
  disabled: boolean;
  defaultText?: string;
  jsonDraft?: string;
  jsonError?: string;
  onUpdate: (name: string, value: JsonValue) => void;
  onRemove: (name: string) => void;
  onJsonDraftChange: (name: string, value: string) => void;
  onJsonBlur: (name: string, value: string) => void;
  onJsonUnset: (name: string) => void;
};

function stringify(value: JsonObject): string {
  return JSON.stringify(value, null, 2);
}

function unsetLabel(field: ParameterHint): string {
  return field.hasDefault ? 'Use default' : 'Unset';
}

function ParameterField({
  field,
  current,
  hasValue,
  wiredFrom,
  disabled,
  defaultText,
  jsonDraft,
  jsonError,
  onUpdate,
  onRemove,
  onJsonDraftChange,
  onJsonBlur,
  onJsonUnset,
}: ParameterFieldProps) {
  let control: ReactNode;
  const choices = field.choices;

  if (wiredFrom) {
    control = <p className="parameter-wired">Connected from <strong>{wiredFrom}</strong></p>;
  } else if (choices?.length) {
    control = <><select id={`parameter-${field.name}`} disabled={disabled}
      value={!hasValue ? '__unset__' : choices.some((choice) => JSON.stringify(choice) === JSON.stringify(current)) ? `choice:${JSON.stringify(current)}` : '__custom__'}
      onChange={(event) => { if (event.target.value === '__unset__') onRemove(field.name); else if (event.target.value.startsWith('choice:')) onUpdate(field.name, JSON.parse(event.target.value.slice(7)) as JsonValue); }}>
      <option value="__unset__">{field.hasDefault ? 'Use default' : 'Unset'}</option>
      {choices.map((choice, index) => <option key={index} value={`choice:${JSON.stringify(choice)}`}>{JSON.stringify(choice)}</option>)}
      {hasValue && <option value="__custom__">Custom value (JSON)</option>}
    </select><button type="button" disabled={disabled} onClick={() => onJsonDraftChange(field.name, JSON.stringify(current ?? null))}>Edit JSON value</button>
    {jsonDraft !== undefined && <textarea aria-label={`${field.name} JSON value`} value={jsonDraft} disabled={disabled} onChange={(event) => onJsonDraftChange(field.name, event.target.value)} onBlur={() => onJsonBlur(field.name, jsonDraft)} />}</>;
  } else {
    switch (field.kind) {
      case 'boolean':
        control = <select
          id={`parameter-${field.name}`}
          disabled={disabled}
          value={!hasValue ? '__default__' : current === true ? 'true' : current === false ? 'false' : 'invalid'}
          onChange={(event) => {
            if (event.target.value === '__default__') onRemove(field.name);
            else if (event.target.value === 'true') onUpdate(field.name, true);
            else if (event.target.value === 'false') onUpdate(field.name, false);
          }}
        >
          <option value="__default__">{unsetLabel(field)}</option>
          <option value="true">True</option>
          <option value="false">False</option>
          {current !== true && current !== false && hasValue && <option value="invalid">Use JSON editor</option>}
        </select>;
        break;
      case 'number':
        control = <>
          <input
            id={`parameter-${field.name}`}
            type="number"
            disabled={disabled}
            value={typeof current === 'number' ? current : ''}
            placeholder={defaultText}
            onChange={(event) => event.target.value === '' ? onRemove(field.name) : onUpdate(field.name, Number(event.target.value))}
          />
          <button type="button" className="parameter-unset" disabled={disabled || !hasValue} onClick={() => onRemove(field.name)}>{unsetLabel(field)}</button>
        </>;
        break;
      case 'string':
        control = choices?.every((choice) => typeof choice === 'string') ? <>
          <select id={`parameter-${field.name}`} disabled={disabled}
            value={!hasValue ? '__default__' : typeof current === 'string' && choices.includes(current) ? current : '__custom__'}
            onChange={(event) => {
              if (event.target.value === '__default__') onRemove(field.name);
              else if (event.target.value !== '__custom__') onUpdate(field.name, event.target.value);
            }}>
            <option value="__default__">{unsetLabel(field)}</option>
            {choices.map((choice) => <option key={choice} value={choice}>{choice}</option>)}
            {hasValue && (typeof current !== 'string' || !choices.includes(current)) && <option value="__custom__">Use JSON editor</option>}
          </select>
        </> : <>
          <input
            id={`parameter-${field.name}`}
            type="text"
            disabled={disabled}
            value={typeof current === 'string' ? current : ''}
            placeholder={defaultText}
            onChange={(event) => onUpdate(field.name, event.target.value)}
          />
          <button type="button" className="parameter-unset" disabled={disabled || !hasValue} onClick={() => onRemove(field.name)}>{unsetLabel(field)}</button>
        </>;
        break;
      case 'json':
        control = <>
          <textarea
            id={`parameter-${field.name}`}
            className="code-area parameter-json"
            disabled={disabled}
            value={jsonDraft ?? (hasValue ? JSON.stringify(current) : '')}
            placeholder={defaultText ?? 'JSON value'}
            onChange={(event) => onJsonDraftChange(field.name, event.target.value)}
            onBlur={(event) => onJsonBlur(field.name, event.target.value)}
          />
          {jsonError && <small className="parameter-error" role="alert">{jsonError}</small>}
          <button type="button" className="parameter-unset" disabled={disabled || !hasValue} onClick={() => onJsonUnset(field.name)}>{unsetLabel(field)}</button>
        </>;
        break;
    }
  }

  return <div className="parameter-field">
    <div className="parameter-label">
      <label htmlFor={`parameter-${field.name}`}>{field.name}{field.annotation ? <small>{field.annotation}</small> : null}</label>
      {field.required && <em>required</em>}
    </div>
    {control}
    {field.nullable && !wiredFrom && <button type="button" disabled={disabled} onClick={() => onUpdate(field.name, null)}>Set null</button>}
    {!wiredFrom && !hasValue && defaultText && <small className="parameter-default">Default: {defaultText}</small>}
  </div>;
}

export function ParameterEditor({ value, onChange, onApply, disabled, hints, wired, onPendingChange }: Props) {
  const [guided, setGuided] = useState(true);
  const [jsonDrafts, setJsonDrafts] = useState<Record<string, string>>({});
  const [jsonErrors, setJsonErrors] = useState<Record<string, string>>({});
  const parsed = useMemo(() => {
    try {
      return { value: parseParameters(value), error: null as string | null };
    } catch (error) {
      return { value: null, error: error instanceof Error ? error.message : String(error) };
    }
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
  const clearJsonState = (name: string) => {
    setJsonDrafts((current) => { const next = { ...current }; delete next[name]; return next; });
    setJsonErrors((current) => { const next = { ...current }; delete next[name]; return next; });
  };
  const applyJsonDraft = (name: string, text: string) => {
    if (text === '') {
      remove(name);
      clearJsonState(name);
      return;
    }
    try {
      update(name, JSON.parse(text) as JsonValue);
      clearJsonState(name);
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
      {hints?.description && <p className="field-help">{hints.description}</p>}
      {fields.map((field) => {
        const current = parsed.value[field.name];
        const hasValue = Object.prototype.hasOwnProperty.call(parsed.value, field.name);
        const defaultText = field.defaultDisplay ?? (Object.prototype.hasOwnProperty.call(field, 'defaultValue') ? JSON.stringify(field.defaultValue) : undefined);
        return <ParameterField
          key={field.name}
          field={field}
          current={current}
          hasValue={hasValue}
          wiredFrom={wired[field.name]}
          disabled={disabled}
          defaultText={defaultText}
          jsonDraft={jsonDrafts[field.name]}
          jsonError={jsonErrors[field.name]}
          onUpdate={update}
          onRemove={remove}
          onJsonDraftChange={(name, text) => setJsonDrafts((drafts) => ({ ...drafts, [name]: text }))}
          onJsonBlur={applyJsonDraft}
          onJsonUnset={(name) => { remove(name); clearJsonState(name); }}
        />;
      })}
    </div> : <>
      <textarea className="code-area" aria-label="Draft parameters" value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} spellCheck={false} aria-describedby="parameter-help" />
      {parsed.error && <p className="parameter-error" role="alert">{parsed.error}</p>}
      <p id="parameter-help" className="field-help">JSON object saved only in this editor draft. Unknown keys are retained.</p>
    </>}
    <Button variant="secondary" className="wide" disabled={disabled || Boolean(parsed.error) || unresolvedJson} onClick={onApply}>Apply parameters</Button>
  </section>;
}
