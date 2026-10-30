import type { DraftEdge, DraftNode, EditorDraft, Point } from './types';

/** A bounded, editor-only draft history. It never records execution state. */
export const HISTORY_LIMIT = 100;

export type DraftHistory = Readonly<{
  past: readonly EditorDraft[];
  present: EditorDraft;
  future: readonly EditorDraft[];
}>;

function copy<T>(value: T): T {
  return structuredClone(value);
}

/** Retained snapshots are immutable; only the live present draft is mutable. */
function retained(draft: EditorDraft): EditorDraft {
  const snapshot = copy(draft);
  const freeze = (value: unknown): void => {
    if (value && typeof value === 'object') {
      Object.values(value).forEach(freeze);
      Object.freeze(value);
    }
  };
  freeze(snapshot);
  return snapshot;
}

function equal(left: EditorDraft, right: EditorDraft): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function createDraftHistory(draft: EditorDraft): DraftHistory {
  return { past: [], present: copy(draft), future: [] };
}

/** Record one completed authoring operation. Callers deliberately omit viewport, selection, and run changes. */
export function commitDraft(history: DraftHistory, next: EditorDraft): DraftHistory {
  const snapshot = copy(next);
  if (equal(history.present, snapshot)) return history;
  return {
    past: [...history.past.slice(-(HISTORY_LIMIT - 1)), retained(history.present)],
    present: snapshot,
    future: [],
  };
}

export function replaceDraftHistory(_history: DraftHistory, draft: EditorDraft): DraftHistory {
  return { past: [], present: copy(draft), future: [] };
}

export function undoDraft(history: DraftHistory): DraftHistory {
  const previous = history.past.at(-1);
  if (!previous) return history;
  return {
    past: history.past.slice(0, -1),
    present: copy(previous),
    future: [retained(history.present), ...history.future],
  };
}

export function redoDraft(history: DraftHistory): DraftHistory {
  const next = history.future[0];
  if (!next) return history;
  return {
    past: [...history.past, retained(history.present)],
    present: copy(next),
    future: history.future.slice(1),
  };
}

export function canUndo(history: DraftHistory): boolean { return history.past.length > 0; }
export function canRedo(history: DraftHistory): boolean { return history.future.length > 0; }

export type DraftClipboard = Readonly<{ nodes: readonly DraftNode[]; edges: readonly DraftEdge[] }>;

export function copySelection(draft: EditorDraft, selectedNodeIds: ReadonlySet<string>): DraftClipboard | null {
  const nodes = draft.nodes.filter((node) => selectedNodeIds.has(node.id));
  if (!nodes.length) return null;
  const ids = new Set(nodes.map((node) => node.id));
  return {
    nodes: copy(nodes),
    // Only preserve a copied group’s internal wiring. Connections to the rest
    // of the canvas would otherwise point at the original selection.
    edges: copy(draft.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target))),
  };
}

let clipboardCounter = 0;
function freshId(prefix: 'node' | 'edge'): string {
  const uuid = globalThis.crypto?.randomUUID?.();
  if (uuid) return `${prefix}-${uuid}`;
  clipboardCounter += 1;
  return `${prefix}-${Date.now().toString(36)}-${clipboardCounter}`;
}

export function pasteSelection(draft: EditorDraft, clipboard: DraftClipboard, offset: Point = { x: 32, y: 32 }): { draft: EditorDraft; nodeIds: Set<string> } {
  if (!clipboard.nodes.length) return { draft, nodeIds: new Set() };
  const ids = new Map<string, string>();
  for (const node of clipboard.nodes) ids.set(node.id, freshId('node'));
  const nodes = clipboard.nodes.map((node) => ({
    ...copy(node),
    id: ids.get(node.id)!,
    position: { x: node.position.x + offset.x, y: node.position.y + offset.y },
  }));
  const edges = clipboard.edges.flatMap((edge) => {
    const source = ids.get(edge.source); const target = ids.get(edge.target);
    return source && target ? [{ ...copy(edge), id: freshId('edge'), source, target }] : [];
  });
  return { draft: { ...copy(draft), nodes: [...draft.nodes.map(copy), ...nodes], edges: [...draft.edges.map(copy), ...edges] }, nodeIds: new Set(nodes.map((node) => node.id)) };
}
