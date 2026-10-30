import { describe, expect, it, vi } from 'vitest';

import { demoCatalog, createDemoDraft } from '../tests/fixtures/demo';
import type { ExecutionGraph } from './types';
import {
  STORAGE_KEY,
  addTask,
  connectNodes,
  canConnectNodes,
  clearEdgeArgument,
  eligibleTargetArguments,
  reconnectNodes,
  createEmptyDraft,
  projectFlowDraft,
  executionGraph,
  flowLayout,
  importMetadata,
  loadStoredDraft,
  parseDraft,
  parseParameters,
  removeNode,
  saveStoredDraft,
  serializeDraft,
  setEdgeArgument,
} from './model';

const digest = 'a'.repeat(64);

function projectSnapshot(): object {
  return {
    schema: 1,
    project: { root: '/workspace/demo', config_path: '/workspace/demo/weavem.toml', store_path: '/store', work_dir: '/work' },
    tasks: [{
      path: '/workspace/demo/tasks/local/task.toml',
      metadata: { schema: 1, task_id: 'demo.same', version: '1.0.0', backend: 'python', source: 'implementation.py', export: 'run', description: null },
    }],
    flows: [{ path: '/workspace/demo/flows/ignored.toml', metadata: { schema: 1, flow_id: 'ignored', version: '1.0.0', tasks: [] } }],
    bindings: [
      { alias: 'local', path: 'tasks/local', release: null, source: 'task-store', manifest_sha256: null },
      { alias: 'released', path: null, release: 'demo.same==1.0.0', source: '/external/store', manifest_sha256: digest },
    ],
    releases: [{
      kind: 'task', root: '/external/store/demo.same/1.0.0', manifest_sha256: digest,
      metadata: { schema: 1, task_id: 'demo.same', version: '1.0.0', backend: 'cython', description: null },
    }],
  };
}

describe('metadata import', () => {
  it('opens a resolved project flow with its literals and argument mappings ready to run', () => {
    const catalog = importMetadata(JSON.stringify(projectSnapshot()));
    const key = catalog.tasks[0].key;
    const graph: ExecutionGraph = {
      kind: 'weavem.graph' as const, schema: 1 as const, name: 'Ready to run',
      nodes: [{ id: 'source', taskKey: key, parameters: { value: 'hello' } },
        { id: 'target', taskKey: key, parameters: {} }],
      edges: [{ id: 'wire', source: 'source', target: 'target', argument: 'value' }],
    };
    const draft = projectFlowDraft(catalog, graph);
    expect(executionGraph(draft, { [key]: 'local' })).toEqual(graph);
    expect(draft.nodes[0].position).not.toEqual(draft.nodes[1].position);
    expect(() => projectFlowDraft(catalog, { ...graph, nodes: [{ ...graph.nodes[0], taskKey: 'unknown' }] })).toThrow(/does not exist/);
  });
  it('imports authored and pinned released tasks, but not flow specs', () => {
    const catalog = importMetadata(JSON.stringify(projectSnapshot()));
    expect(catalog).toMatchObject({ kind: 'project', name: '/workspace/demo' });
    expect(catalog.tasks).toHaveLength(2);
    expect(catalog.tasks.map((task) => task.key)).toEqual([
      'local:/workspace/demo/tasks/local/task.toml',
      `released:/external/store/demo.same/1.0.0:${digest}`,
    ]);
    expect(catalog.tasks[0]).toMatchObject({ description: '', inputs: [], output: 'Any', provenance: 'local' });
    expect(catalog.tasks[1]).toMatchObject({ provenance: 'released', backend: 'cython', manifestSha256: digest });
  });

  it('keeps source and released tasks distinct even when identity matches', () => {
    const catalog = importMetadata(JSON.stringify(projectSnapshot()));
    expect(catalog.tasks[0].taskId).toBe(catalog.tasks[1].taskId);
    expect(catalog.tasks[0].version).toBe(catalog.tasks[1].version);
    expect(catalog.tasks[0].key).not.toBe(catalog.tasks[1].key);
  });

  it('keeps all root-distinct releases matched by the same identity and digest', () => {
    const snapshot = projectSnapshot() as { releases: Array<Record<string, unknown>> };
    snapshot.releases.push({ ...snapshot.releases[0], root: '/another/store/demo.same/1.0.0' });
    const catalog = importMetadata(JSON.stringify(snapshot));
    expect(catalog.tasks.filter((task) => task.provenance === 'released').map((task) => task.key)).toEqual([
      `released:/external/store/demo.same/1.0.0:${digest}`,
      `released:/another/store/demo.same/1.0.0:${digest}`,
    ]);
  });

  it('keeps releases with the same identity but different pinned digests', () => {
    const secondDigest = 'b'.repeat(64);
    const snapshot = projectSnapshot() as { bindings: Array<Record<string, unknown>>; releases: Array<Record<string, unknown>> };
    snapshot.bindings.push({ alias: 'second-release', path: null, release: 'demo.same==1.0.0', source: '/another/store', manifest_sha256: secondDigest });
    snapshot.releases.push({ ...snapshot.releases[0], root: '/another/store/demo.same/1.0.0', manifest_sha256: secondDigest });
    const catalog = importMetadata(JSON.stringify(snapshot));
    expect(catalog.tasks.filter((task) => task.provenance === 'released')).toHaveLength(2);
    expect(catalog.tasks.map((task) => task.key)).toContain(`released:/another/store/demo.same/1.0.0:${secondDigest}`);
  });

  it('rejects snapshots whose release binding is not part of the release data', () => {
    const broken = projectSnapshot() as { bindings: Array<{ release: string | null }> };
    broken.bindings[1].release = 'different.task==1.0.0';
    expect(() => importMetadata(JSON.stringify(broken))).toThrow(/do not match an imported release/);
  });

  it('does not mutate a supplied metadata snapshot when import fails', () => {
    const snapshot = projectSnapshot() as { tasks: Array<{ metadata: Record<string, unknown> }> };
    snapshot.tasks[0].metadata.backend = 'rust';
    const before = JSON.stringify(snapshot);
    expect(() => importMetadata(JSON.stringify(snapshot))).toThrow(/python or cython/);
    expect(JSON.stringify(snapshot)).toBe(before);
  });
});

describe('draft model', () => {
  it('round trips every editor-owned field through stable JSON', () => {
    const initial = createDemoDraft();
    const added = addTask(initial, demoCatalog.tasks[0].key, { x: 12, y: 34 });
    const changed = {
      ...added,
      viewport: { x: 1, y: -3, zoom: 1.25 },
      nodes: added.nodes.map((node, index) => index === 0 ? { ...node, notes: 'kept', parameters: { nested: { value: true } } } : node),
    };
    const serialized = serializeDraft(changed);
    expect(serializeDraft(parseDraft(serialized))).toBe(serialized);
    expect(parseDraft(serialized).nodes[0]).toMatchObject({ notes: 'kept', parameters: { nested: { value: true } } });
  });

  it('round trips a deliberately blank in-progress draft name', () => {
    const draft = { ...createEmptyDraft(demoCatalog), name: '' };
    expect(parseDraft(serializeDraft(draft)).name).toBe('');
  });

  it('does not mutate a draft while adding or deleting nodes', () => {
    const empty = createEmptyDraft(demoCatalog);
    const added = addTask(empty, demoCatalog.tasks[0].key, { x: 1, y: 2 });
    expect(empty.nodes).toEqual([]);
    const removed = removeNode(added, added.nodes[0].id);
    expect(added.nodes).toHaveLength(1);
    expect(removed.nodes).toEqual([]);
  });

  it('allows cycles but rejects self, duplicate, and dangling connections', () => {
    const one = addTask(createEmptyDraft(demoCatalog), demoCatalog.tasks[0].key);
    const two = addTask(one, demoCatalog.tasks[1].key);
    const forward = connectNodes(two, two.nodes[0].id, two.nodes[1].id);
    const cyclic = connectNodes(forward, two.nodes[1].id, two.nodes[0].id);
    expect(cyclic.edges).toHaveLength(2);
    expect(() => connectNodes(forward, two.nodes[0].id, two.nodes[0].id)).toThrow(/itself/);
    expect(() => connectNodes(forward, two.nodes[0].id, two.nodes[1].id)).toThrow(/already exists/);
    expect(() => connectNodes(forward, 'missing', two.nodes[1].id)).toThrow(/nodes in this draft/);
  });

  it('keeps canvas and inspector connection data in one draft edge list', () => {
    const draft = createDemoDraft();
    expect(draft.edges.filter((edge) => edge.target === 'demo-normalize')).toMatchObject([{ source: 'demo-read' }]);
    expect(draft.edges.filter((edge) => edge.source === 'demo-normalize')).toMatchObject([{ target: 'demo-count' }]);
  });

  it('shares add eligibility with pointer connections and rejects duplicate unmapped wires', () => {
    const draft = createDemoDraft();
    expect(canConnectNodes(draft, 'demo-read', 'demo-read')).toBe(false);
    expect(canConnectNodes(draft, 'missing', 'demo-count')).toBe(false);
    expect(canConnectNodes(draft, 'demo-read', 'demo-normalize')).toBe(false);
    expect(() => connectNodes(draft, 'demo-read', 'demo-normalize')).toThrow(/already exists/);
    const disconnected = { ...draft, edges: draft.edges.filter((edge) => edge.source !== 'demo-read') };
    expect(canConnectNodes(disconnected, 'demo-read', 'demo-normalize')).toBe(true);
    const linked = connectNodes(disconnected, 'demo-read', 'demo-normalize');
    expect(canConnectNodes(linked, 'demo-read', 'demo-normalize')).toBe(false);
  });

  it('still permits another wire to a distinct available input on an already connected task', () => {
    const draft = createDemoDraft();
    draft.catalog.tasks.find((task) => task.taskId === 'text.normalize')!.inputs = ['documents', 'extra'];
    draft.edges[0].argument = 'documents';
    expect(canConnectNodes(draft, 'demo-read', 'demo-normalize')).toBe(true);
    const linked = connectNodes(draft, 'demo-read', 'demo-normalize');
    expect(linked.edges.at(-1)?.argument).toBe('extra');
    expect(canConnectNodes(linked, 'demo-read', 'demo-normalize')).toBe(false);
  });

  it('suggests exactly one unused named input and resets a changed reconnect target', () => {
    const one = addTask(createEmptyDraft(demoCatalog), demoCatalog.tasks[0].key);
    const two = addTask(one, demoCatalog.tasks[1].key);
    const linked = connectNodes(two, one.nodes[0].id, two.nodes[1].id);
    expect(linked.edges[0].argument).toBe('documents');
    expect(eligibleTargetArguments(linked, two.nodes[1].id)).toEqual([]);
    const third = addTask(linked, demoCatalog.tasks[2].key);
    const moved = reconnectNodes(third, linked.edges[0].id, one.nodes[0].id, third.nodes[2].id);
    expect(moved.edges[0].argument).toBe('normalized_documents');
  });

  it('recognizes a conservative name-and-annotation input description', () => {
    const catalog = { ...demoCatalog, tasks: [demoCatalog.tasks[0], { ...demoCatalog.tasks[1], inputs: ['text: str', 'natural language prose'] }] };
    const first = addTask(createEmptyDraft(catalog), catalog.tasks[0].key);
    const second = addTask(first, catalog.tasks[1].key);
    expect(connectNodes(second, first.nodes[0].id, second.nodes[1].id).edges[0].argument).toBe('text');
  });

  it('can clear a mapping without deleting its wire', () => {
    const mapped = setEdgeArgument(createDemoDraft(), 'demo-edge-read-normalize', 'documents');
    expect(clearEdgeArgument(mapped, 'demo-edge-read-normalize').edges[0].argument).toBeUndefined();
  });

  it('preserves an edge mapping when only its source reconnects', () => {
    const draft = setEdgeArgument(createDemoDraft(), 'demo-edge-read-normalize', 'documents');
    const moved = reconnectNodes(draft, 'demo-edge-read-normalize', 'demo-count', 'demo-normalize');
    expect(moved.edges.find((edge) => edge.id === 'demo-edge-read-normalize')?.argument).toBe('documents');
  });

  it('migrates schema 1 generic wires to schema 3 without inventing argument mappings', () => {
    const legacy = createDemoDraft() as unknown as { schema: number };
    legacy.schema = 1;
    const migrated = parseDraft(JSON.stringify(legacy));
    expect(migrated.schema).toBe(3);
    expect(migrated.edges[0].argument).toBeUndefined();
  });

  it('creates a runnable graph only when bound, mapped, and acyclic', () => {
    const catalog = { ...demoCatalog, kind: 'project' as const, name: '/project' };
    const one = addTask(createEmptyDraft(catalog), catalog.tasks[0].key);
    const two = addTask(one, catalog.tasks[1].key);
    const linked = connectNodes(two, two.nodes[0].id, two.nodes[1].id);
    const bindings = Object.fromEntries(catalog.tasks.map((task) => [task.key, 'alias']));
    expect(executionGraph(linked, bindings)).toMatchObject({ edges: [{ argument: 'documents' }] });
    const mapped = setEdgeArgument(linked, linked.edges[0].id, 'documents');
    expect(executionGraph(mapped, bindings)).toMatchObject({ kind: 'weavem.graph', schema: 1, edges: [{ argument: 'documents' }] });
    const reverse = connectNodes(mapped, mapped.nodes[1].id, mapped.nodes[0].id);
    const cycle = setEdgeArgument(reverse, reverse.edges[1].id, 'back');
    expect(() => executionGraph(cycle, bindings)).toThrow(/cycles/);
    expect(() => executionGraph(mapped, {})).toThrow(/not bound/);
    expect(() => executionGraph(setEdgeArgument(linked, linked.edges[0].id, 'not-valid'), bindings)).toThrow(/valid Python argument/);
    expect(() => executionGraph(setEdgeArgument(linked, linked.edges[0].id, 'return_state'), bindings)).toThrow(/valid Python argument/);
    const literalConflict = { ...mapped, nodes: mapped.nodes.map((node) => node.id === mapped.nodes[1].id ? { ...node, parameters: { documents: 'literal' } } : node) };
    expect(() => executionGraph(literalConflict, bindings)).toThrow(/conflicts with a literal/);
  });

  it('removes all incident edges with a node', () => {
    const draft = createDemoDraft();
    const result = removeNode(draft, 'demo-normalize');
    expect(result.nodes.map((node) => node.id)).not.toContain('demo-normalize');
    expect(result.edges).toEqual([]);
    expect(draft.edges).toHaveLength(2);
  });

  it('rejects malformed drafts, invalid references and non-finite editor values', () => {
    const draft = createEmptyDraft(demoCatalog);
    expect(() => parseDraft('{')).toThrow(/valid JSON/);
    expect(() => parseDraft(JSON.stringify({ ...draft, nodes: [{ id: 'a', taskKey: 'unknown', position: { x: 0, y: 0 }, label: '', notes: '', parameters: {} }] }))).toThrow(/does not exist/);
    expect(() => parseDraft(JSON.stringify({ ...draft, viewport: { x: 0, y: 0, zoom: 0 } }))).toThrow(/greater than zero/);
    expect(() => parseDraft(JSON.stringify({ ...draft, catalog: { ...draft.catalog, tasks: [{ ...draft.catalog.tasks[0], backend: 'rust' }] } }))).toThrow(/python or cython/);
    const node = { id: 'same', taskKey: demoCatalog.tasks[0].key, position: { x: 0, y: 0 }, label: '', notes: '', parameters: {} };
    expect(() => parseDraft(JSON.stringify({ ...draft, nodes: [node, node] }))).toThrow(/duplicate id/);
    expect(() => parseDraft(JSON.stringify({ ...draft, nodes: [node, { ...node, id: 'other' }], edges: [{ id: 'edge', source: 'same', target: 'other' }, { id: 'edge', source: 'other', target: 'same' }] }))).toThrow(/duplicate id/);
  });

  it('creates usable unique IDs where crypto.randomUUID is unavailable', () => {
    vi.stubGlobal('crypto', undefined);
    try {
      const first = addTask(createEmptyDraft(demoCatalog), demoCatalog.tasks[0].key);
      const second = addTask(first, demoCatalog.tasks[0].key);
      expect(first.nodes[0].id).toMatch(/^node-/);
      expect(second.nodes[1].id).toMatch(/^node-/);
      expect(second.nodes[0].id).not.toBe(second.nodes[1].id);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe('parameters and browser storage', () => {
  it('only accepts a JSON object for parameters', () => {
    expect(parseParameters('{"active":true,"items":[1,2]}')).toEqual({ active: true, items: [1, 2] });
    expect(() => parseParameters('not-json')).toThrow(/valid JSON/);
    expect(() => parseParameters('[]')).toThrow(/JSON object/);
  });

  it('leaves corrupt storage untouched and exposes a human-readable error', () => {
    let writes = 0;
    const storage = { getItem: () => '{broken', setItem: () => { writes += 1; } };
    const result = loadStoredDraft(storage);
    expect(result.draft).toBeNull();
    expect(result.error).toMatch(/Could not load saved draft/);
    expect(writes).toBe(0);
  });

  it('reports quota failures without overwriting storage', () => {
    let writes = 0;
    const storage = { setItem: () => { writes += 1; throw new Error('quota exceeded'); } };
    const result = saveStoredDraft(storage, createEmptyDraft(demoCatalog));
    expect(result.error).toMatch(/quota exceeded/);
    expect(writes).toBe(1);
  });

  it('uses the documented storage key', () => {
    let key = '';
    const storage = { setItem: (nextKey: string) => { key = nextKey; } };
    saveStoredDraft(storage, createEmptyDraft(demoCatalog));
    expect(key).toBe(STORAGE_KEY);
  });
});

describe('project flow presentation', () => {
  it('keeps layout presentation separate from the executable graph', () => {
    const catalog = importMetadata(JSON.stringify(projectSnapshot()));
    const graph: ExecutionGraph = {
      kind: 'weavem.graph', schema: 1, name: 'visual_flow',
      nodes: [{ id: 'first', taskKey: catalog.tasks[0].key, parameters: { value: 'hello' } }], edges: [],
    };
    const draft = projectFlowDraft(catalog, graph, {
      schema: 1, viewport: { x: 8, y: 9, zoom: 1.25 },
      nodes: [{ id: 'first', position: { x: 70, y: 80 }, label: 'Custom title', notes: 'Canvas only' }],
    });
    expect(draft.nodes[0]).toMatchObject({ position: { x: 70, y: 80 }, label: 'Custom title', notes: 'Canvas only' });
    expect(flowLayout(draft)).toEqual({
      schema: 1, viewport: { x: 8, y: 9, zoom: 1.25 },
      nodes: [{ id: 'first', position: { x: 70, y: 80 }, label: 'Custom title', notes: 'Canvas only' }],
    });
    expect(executionGraph(draft, { [catalog.tasks[0].key]: 'local' })).toEqual(graph);
  });
});

// A field reference is saved as code semantics, never dropped as UI metadata.
it('preserves indexed upstream paths across draft import and executable graph conversion', () => {
  const draft = createDemoDraft();
  draft.edges[0].argument = 'text';
  draft.edges[0].sourcePath = ['customers', 0, 'email'];
  const reopened = parseDraft(serializeDraft(draft));
  expect(reopened.edges[0].sourcePath).toEqual(['customers', 0, 'email']);
});
