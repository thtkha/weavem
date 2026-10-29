import type { ChangeEvent, ReactNode } from 'react';
import type { FlowSummary } from '../types';
import { Button } from './Button';

export type EditorToolbarProps = {
  busy: boolean; isProjectFlow: boolean; canEdit: boolean; flowName: string;
  onFlowNameChange: (name: string) => void; onNew: () => void; onImportMetadata: () => void;
  onOpenFlow: (name: string) => void; flows: readonly FlowSummary[]; onSave: () => void; onSaveAs: () => void;
  onOpenDraft: () => void; onExportDraft: () => void; onConnectProject: () => void; connected: boolean;
  canUndo: boolean; canRedo: boolean; canCopy: boolean; canPaste: boolean;
  onUndo: () => void; onRedo: () => void; onCopy: () => void; onPaste: () => void;
  runParameters: string; onRunParametersChange: (value: string) => void; canRun: boolean; runControl: ReactNode;
  icons?: Partial<Record<'plus' | 'file' | 'folder' | 'download' | 'undo' | 'redo' | 'copy' | 'paste', ReactNode>>;
};
function icon(icons: EditorToolbarProps['icons'], name: keyof NonNullable<EditorToolbarProps['icons']>): ReactNode { return icons?.[name] ?? null; }

/** Presentational toolbar; its host owns persistence, dialogs, shortcuts, and execution. */
export function EditorToolbar(props: EditorToolbarProps) {
  const { busy, isProjectFlow, canEdit, flowName, onFlowNameChange, onNew, onImportMetadata, onOpenFlow, flows, onSave, onSaveAs, onOpenDraft, onExportDraft, onConnectProject, connected, canUndo, canRedo, canCopy, canPaste, onUndo, onRedo, onCopy, onPaste, runParameters, onRunParametersChange, canRun, runControl, icons } = props;
  const disabledFlowEdit = busy || !canEdit;
  return <div className="editor-toolbar" role="group" aria-label="Flow actions">
    <section className="toolbar-group toolbar-group-flow" aria-label="Flow authoring">
      <label className="toolbar-flow-name"><span>Flow name</span><input aria-label="Flow name" disabled={disabledFlowEdit} value={flowName} onChange={(event: ChangeEvent<HTMLInputElement>) => onFlowNameChange(event.target.value)} /></label>
      <Button disabled={busy || !isProjectFlow} onClick={onNew}>{icon(icons, 'plus')} {isProjectFlow ? 'New flow' : 'New draft'}</Button>
      <label className="flow-picker"><span className="visually-hidden">Open project flow</span><select aria-label="Open project flow" disabled={busy || !isProjectFlow || flows.length === 0} value="" onChange={(event) => { if (event.target.value) onOpenFlow(event.target.value); }}><option value="">Open flow…</option>{flows.map((item) => <option key={item.name} value={item.name}>{item.name}{item.editable ? '' : ' (source only)'}</option>)}</select></label>
      <Button variant="primary" disabled={disabledFlowEdit || !isProjectFlow} onClick={onSave}>{icon(icons, 'file')} Save</Button>
      <Button disabled={disabledFlowEdit || !isProjectFlow} onClick={onSaveAs}>Save as</Button>
    </section>
    <section className="toolbar-group toolbar-group-edit" aria-label="Edit history">
      <Button aria-label="Undo" title="Undo (Ctrl/Cmd+Z)" disabled={busy || !canUndo} onClick={onUndo}>{icon(icons, 'undo')} Undo</Button>
      <Button aria-label="Redo" title="Redo (Ctrl/Cmd+Shift+Z)" disabled={busy || !canRedo} onClick={onRedo}>{icon(icons, 'redo')} Redo</Button>
      <Button aria-label="Copy selection" title="Copy selection (Ctrl/Cmd+C)" disabled={busy || !canCopy} onClick={onCopy}>{icon(icons, 'copy')} Copy</Button>
      <Button aria-label="Paste selection" title="Paste selection (Ctrl/Cmd+V)" disabled={busy || !canPaste} onClick={onPaste}>{icon(icons, 'paste')} Paste</Button>
    </section>
    <details className="toolbar-overflow"><summary aria-label="More flow actions">More</summary><div className="toolbar-overflow-menu"><Button disabled={busy} onClick={onImportMetadata}>{icon(icons, 'file')} Import metadata</Button><Button disabled={busy} onClick={onOpenDraft}>{icon(icons, 'folder')} Open draft</Button><Button onClick={onExportDraft}>{icon(icons, 'download')} Export draft</Button><Button disabled={busy} onClick={onConnectProject}>{connected ? 'Refresh project' : 'Connect project'}</Button></div></details>
    <section className="toolbar-group toolbar-group-run" aria-label="Flow execution"><label className="run-parameters"><span>Run parameters</span><input aria-label="Run parameters JSON" disabled={busy || !isProjectFlow} value={runParameters} onChange={(event) => onRunParametersChange(event.target.value)} placeholder="{}" /></label><div className="run-actions" aria-disabled={!canRun && !busy}>{runControl}</div></section>
  </div>;
}
