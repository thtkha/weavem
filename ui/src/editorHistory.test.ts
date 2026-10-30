import { describe, expect, it } from 'vitest';
import { createDemoDraft } from './model';
import { canRedo, canUndo, commitDraft, copySelection, createDraftHistory, pasteSelection, redoDraft, undoDraft } from './editorHistory';

describe('draft history', () => {
  it('undoes, redoes, and drops redo after a new authoring action', () => {
    const initial = createDemoDraft();
    const renamed = { ...initial, name: 'Changed' };
    let history = commitDraft(createDraftHistory(initial), renamed);
    expect(canUndo(history)).toBe(true);
    history = undoDraft(history);
    expect(history.present.name).toBe(initial.name);
    expect(canRedo(history)).toBe(true);
    history = redoDraft(history);
    expect(history.present.name).toBe('Changed');
    history = undoDraft(history);
    history = commitDraft(history, { ...history.present, name: 'Other' });
    expect(canRedo(history)).toBe(false);
  });

  it('copies only internal wires and pastes fresh identities with an offset', () => {
    const draft = createDemoDraft();
    const clipboard = copySelection(draft, new Set(['demo-normalize', 'demo-count']));
    expect(clipboard?.edges).toHaveLength(1);
    const pasted = pasteSelection(draft, clipboard!);
    expect(pasted.draft.nodes).toHaveLength(draft.nodes.length + 2);
    expect([...pasted.nodeIds].every((id) => !draft.nodes.some((node) => node.id === id))).toBe(true);
    const copiedFirst = pasted.draft.nodes.find((node) => pasted.nodeIds.has(node.id))!;
    expect(copiedFirst.position.x).toBeGreaterThanOrEqual(32);
    expect(pasted.draft.edges).toHaveLength(draft.edges.length + 1);
  });
});

it('isolates live drafts from saved history during undo and redo', () => {
  const initial = createDemoDraft();
  let history = createDraftHistory(initial);
  initial.name = 'external mutation';
  expect(history.present.name).not.toBe(initial.name);
  history = commitDraft(history, { ...history.present, name: 'second' });
  history = commitDraft(history, { ...history.present, name: 'third' });
  const undone = undoDraft(history);
  undone.present.name = 'changed live draft';
  expect(history.past.at(-1)?.name).toBe('second');
  const redone = redoDraft(undone);
  redone.present.name = 'changed again';
  expect(undone.future[0].name).toBe('third');
});

it('shares only frozen retained snapshots between history versions', () => {
  let history = createDraftHistory(createDemoDraft());
  history = commitDraft(history, { ...history.present, name: 'second' });
  history = commitDraft(history, { ...history.present, name: 'third' });
  const undone = undoDraft(history);
  expect(undone.past[0]).toBe(history.past[0]);
  expect(Object.isFrozen(undone.past[0].nodes)).toBe(true);
  expect(() => { undone.past[0].name = 'corruption'; }).toThrow();
  expect(history.past[0].name).not.toBe('corruption');
});
