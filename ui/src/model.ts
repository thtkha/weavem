import type {
  Catalog,
  CatalogTask,
  DraftEdge,
  DraftNode,
  EditorDraft,
  ExecutionGraph,
  FlowLayout,
  JsonObject,
  JsonValue,
  Point,
  Viewport,
} from './types';

/** Browser-local recovery key, retained across editor versions. */
export const STORAGE_KEY = 'weavem.node-editor.draft.v1';

const DRAFT_KIND = 'weavem.editor-draft';
const DRAFT_SCHEMA = 3;
let idCounter = 0;

type UnknownRecord = Record<string, unknown>;

function fail(message: string): never {
  throw new Error(message);
}

function record(value: unknown, name: string): UnknownRecord {
  if (value === null || Array.isArray(value) || typeof value !== 'object') {
    fail(`${name} must be a JSON object`);
  }
  return value as UnknownRecord;
}

function string(value: unknown, name: string, { empty = false }: { empty?: boolean } = {}): string {
  if (typeof value !== 'string' || (!empty && value.length === 0)) {
    fail(`${name} must be ${empty ? 'a string' : 'a non-empty string'}`);
  }
  return value;
}

function optionalString(value: unknown, name: string): string | undefined {
  if (value === undefined) return undefined;
  return string(value, name);
}

function finiteNumber(value: unknown, name: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) fail(`${name} must be a finite number`);
  return value;
}

function jsonValue(value: unknown, name: string): JsonValue {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return value;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) fail(`${name} must contain finite JSON numbers`);
    return value;
  }
  if (Array.isArray(value)) return value.map((item, index) => jsonValue(item, `${name}[${index}]`));
  const object = record(value, name);
  return Object.fromEntries(Object.entries(object).map(([key, item]) => [key, jsonValue(item, `${name}.${key}`)]));
}

function jsonObject(value: unknown, name: string): JsonObject {
  const object = record(value, name);
  return Object.fromEntries(Object.entries(object).map(([key, item]) => [key, jsonValue(item, `${name}.${key}`)]));
}

function strings(value: unknown, name: string, { defaultValue }: { defaultValue: string[] }): string[] {
  if (value === undefined) return [...defaultValue];
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string' || item.length === 0)) {
    fail(`${name} must be an array of non-empty strings`);
  }
  return [...value] as string[];
}

function point(value: unknown, name: string): Point {
  const object = record(value, name);
  return { x: finiteNumber(object.x, `${name}.x`), y: finiteNumber(object.y, `${name}.y`) };
}

function viewport(value: unknown, name: string): Viewport {
  const result = point(value, name);
  const zoom = finiteNumber(record(value, name).zoom, `${name}.zoom`);
  if (zoom <= 0) fail(`${name}.zoom must be greater than zero`);
  return { ...result, zoom };
}

function sourceTask(metadataValue: unknown, pathValue: unknown, index: number): CatalogTask {
  const metadata = record(metadataValue, `tasks[${index}].metadata`);
  const path = string(pathValue, `tasks[${index}].path`);
  const taskId = string(metadata.task_id, `tasks[${index}].metadata.task_id`);
  const version = string(metadata.version, `tasks[${index}].metadata.version`);
  const backend = metadata.backend ?? 'python';
  if (backend !== 'python' && backend !== 'cython') fail(`tasks[${index}].metadata.backend must be python or cython`);
  const description = metadata.description;
  if (description !== undefined && description !== null && typeof description !== 'string') {
    fail(`tasks[${index}].metadata.description must be a string or null`);
  }
  return {
    key: `local:${path}`,
    taskId,
    version,
    backend,
    provenance: 'local',
    description: description ?? '',
    inputs: strings(metadata.inputs, `tasks[${index}].metadata.inputs`, { defaultValue: [] }),
    output: metadata.output === undefined ? 'Any' : string(metadata.output, `tasks[${index}].metadata.output`),
    source: path,
  };
}

function releasedTask(releaseValue: unknown, index: number): CatalogTask {
  const release = record(releaseValue, `releases[${index}]`);
  if (release.kind !== 'task') fail(`releases[${index}].kind must be task`);
  const root = string(release.root, `releases[${index}].root`);
  const manifestSha256 = string(release.manifest_sha256, `releases[${index}].manifest_sha256`);
  const metadata = record(release.metadata, `releases[${index}].metadata`);
  const taskId = string(metadata.task_id, `releases[${index}].metadata.task_id`);
  const version = string(metadata.version, `releases[${index}].metadata.version`);
  const backend = metadata.backend;
  if (backend !== 'python' && backend !== 'cython') fail(`releases[${index}].metadata.backend must be python or cython`);
  const description = metadata.description;
  if (description !== undefined && description !== null && typeof description !== 'string') {
    fail(`releases[${index}].metadata.description must be a string or null`);
  }
  return {
    key: `released:${root}:${manifestSha256}`,
    taskId,
    version,
    backend,
    provenance: 'released',
    description: description ?? '',
    inputs: strings(metadata.inputs, `releases[${index}].metadata.inputs`, { defaultValue: [] }),
    output: metadata.output === undefined ? 'Any' : string(metadata.output, `releases[${index}].metadata.output`),
    source: root,
    manifestSha256,
  };
}

function taskIdentity(task: CatalogTask): string {
  return `${task.taskId}==${task.version}`;
}

/**
 * Turn a read-only `Project.metadata()` schema-1 snapshot into the editor's
 * intentionally smaller catalog. It imports metadata only; it never imports
 * task or flow code and treats flow specs as out of scope for the editor.
 */
export function importMetadata(text: string): Catalog {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    fail('Metadata import is not valid JSON');
  }
  const snapshot = record(parsed, 'Metadata import');
  if (snapshot.schema !== 1) fail('Metadata import must use project schema 1');
  const project = record(snapshot.project, 'Metadata import.project');
  const root = string(project.root, 'Metadata import.project.root');
  if (!Array.isArray(snapshot.tasks)) fail('Metadata import.tasks must be an array');
  if (!Array.isArray(snapshot.releases)) fail('Metadata import.releases must be an array');
  if (!Array.isArray(snapshot.bindings)) fail('Metadata import.bindings must be an array');
  if (!Array.isArray(snapshot.flows)) fail('Metadata import.flows must be an array');

  const tasks = snapshot.tasks.map((entry, index) => {
    const entryObject = record(entry, `tasks[${index}]`);
    return sourceTask(entryObject.metadata, entryObject.path, index);
  });
  const releases = snapshot.releases.map(releasedTask);
  const releasesByPin = new Map<string, CatalogTask[]>();
  for (const item of releases) {
    const pin = `${taskIdentity(item)}\u0000${item.manifestSha256}`;
    releasesByPin.set(pin, [...(releasesByPin.get(pin) ?? []), item]);
  }

  // A Project snapshot lists release artifacts for bindings. Confirm every
  // released item is represented by a valid pinned binding before displaying it.
  const boundReleases = new Set<string>();
  snapshot.bindings.forEach((bindingValue, index) => {
    const binding = record(bindingValue, `bindings[${index}]`);
    string(binding.alias, `bindings[${index}].alias`);
    if (binding.release === null || binding.release === undefined) return;
    const release = string(binding.release, `bindings[${index}].release`);
    const digest = string(binding.manifest_sha256, `bindings[${index}].manifest_sha256`);
    const matchingReleases = releasesByPin.get(`${release}\u0000${digest}`);
    if (!matchingReleases?.length) {
      fail(`bindings[${index}].release and manifest_sha256 do not match an imported release`);
    }
    // A pin declares an artifact digest, not a unique store location. Preserve
    // every matching root so the editor does not silently collapse stores.
    matchingReleases.forEach((item) => boundReleases.add(item.key));
  });
  const catalogTasks = [...tasks, ...releases.filter((item) => boundReleases.has(item.key))];
  const keys = new Set<string>();
  for (const task of catalogTasks) {
    if (keys.has(task.key)) fail(`Metadata import contains duplicate task source: ${task.source}`);
    keys.add(task.key);
  }
  return { name: root, kind: 'project', tasks: catalogTasks };
}

function validateCatalog(value: unknown, name: string): Catalog {
  const catalog = record(value, name);
  const kind = catalog.kind;
  if (kind !== 'demo' && kind !== 'project') fail(`${name}.kind must be demo or project`);
  const catalogName = string(catalog.name, `${name}.name`);
  if (!Array.isArray(catalog.tasks)) fail(`${name}.tasks must be an array`);
  const keys = new Set<string>();
  const tasks = catalog.tasks.map((taskValue, index): CatalogTask => {
    const task = record(taskValue, `${name}.tasks[${index}]`);
    const key = string(task.key, `${name}.tasks[${index}].key`);
    if (keys.has(key)) fail(`${name}.tasks contains duplicate task key: ${key}`);
    keys.add(key);
    const backend = task.backend;
    if (backend !== 'python' && backend !== 'cython') fail(`${name}.tasks[${index}].backend must be python or cython`);
    const provenance = task.provenance;
    if (provenance !== 'local' && provenance !== 'released') fail(`${name}.tasks[${index}].provenance must be local or released`);
    const manifestSha256 = optionalString(task.manifestSha256, `${name}.tasks[${index}].manifestSha256`);
    if (provenance === 'released' && manifestSha256 === undefined) fail(`${name}.tasks[${index}].manifestSha256 is required for released tasks`);
    if (provenance === 'local' && manifestSha256 !== undefined) fail(`${name}.tasks[${index}].manifestSha256 is only valid for released tasks`);
    return {
      key,
      taskId: string(task.taskId, `${name}.tasks[${index}].taskId`),
      version: string(task.version, `${name}.tasks[${index}].version`),
      backend,
      provenance,
      description: string(task.description, `${name}.tasks[${index}].description`, { empty: true }),
      inputs: strings(task.inputs, `${name}.tasks[${index}].inputs`, { defaultValue: [] }),
      output: string(task.output, `${name}.tasks[${index}].output`),
      source: string(task.source, `${name}.tasks[${index}].source`),
      ...(manifestSha256 === undefined ? {} : { manifestSha256 }),
    };
  });
  return { name: catalogName, kind, tasks };
}

function validateDraft(value: unknown): EditorDraft {
  const draft = record(value, 'Draft');
  if (draft.kind !== DRAFT_KIND) fail(`Draft.kind must be ${DRAFT_KIND}`);
  if (draft.schema !== 1 && draft.schema !== 2 && draft.schema !== DRAFT_SCHEMA) fail('Draft.schema must be 1, 2 or 3');
  const catalog = validateCatalog(draft.catalog, 'Draft.catalog');
  if (!Array.isArray(draft.nodes)) fail('Draft.nodes must be an array');
  if (!Array.isArray(draft.edges)) fail('Draft.edges must be an array');
  const keys = new Set(catalog.tasks.map((task) => task.key));
  const nodeIds = new Set<string>();
  const nodes = draft.nodes.map((nodeValue, index): DraftNode => {
    const node = record(nodeValue, `Draft.nodes[${index}]`);
    const id = string(node.id, `Draft.nodes[${index}].id`);
    if (nodeIds.has(id)) fail(`Draft.nodes contains duplicate id: ${id}`);
    nodeIds.add(id);
    const taskKey = string(node.taskKey, `Draft.nodes[${index}].taskKey`);
    if (!keys.has(taskKey)) fail(`Draft.nodes[${index}].taskKey does not exist in Draft.catalog`);
    return {
      id,
      taskKey,
      position: point(node.position, `Draft.nodes[${index}].position`),
      label: string(node.label, `Draft.nodes[${index}].label`, { empty: true }),
      notes: string(node.notes, `Draft.nodes[${index}].notes`, { empty: true }),
      parameters: jsonObject(node.parameters, `Draft.nodes[${index}].parameters`),
    };
  });
  const edgeIds = new Set<string>();
  const links = new Set<string>();
  const edges = draft.edges.map((edgeValue, index): DraftEdge => {
    const edge = record(edgeValue, `Draft.edges[${index}]`);
    const id = string(edge.id, `Draft.edges[${index}].id`);
    if (edgeIds.has(id)) fail(`Draft.edges contains duplicate id: ${id}`);
    edgeIds.add(id);
    const source = string(edge.source, `Draft.edges[${index}].source`);
    const target = string(edge.target, `Draft.edges[${index}].target`);
    if (source === target) fail(`Draft.edges[${index}] cannot link a node to itself`);
    if (!nodeIds.has(source) || !nodeIds.has(target)) fail(`Draft.edges[${index}] references an unknown node`);
    const argument = edge.argument === undefined ? undefined : string(edge.argument, `Draft.edges[${index}].argument`);
    const sourcePath = edge.sourcePath;
    if (sourcePath !== undefined && (!Array.isArray(sourcePath) || sourcePath.length > 32 || sourcePath.some((part) => typeof part !== 'string' && !(typeof part === 'number' && Number.isSafeInteger(part) && part >= 0)))) fail('Connection sourcePath must contain string keys or non-negative integer indexes');
    const link = JSON.stringify([source, target, argument ?? '']);
    if (links.has(link)) fail(`Draft.edges contains duplicate connection: ${source} to ${target}`);
    links.add(link);
    return { id, source, target, ...(argument === undefined ? {} : { argument }), ...(sourcePath === undefined ? {} : { sourcePath: sourcePath as Array<string | number> }) };
  });
  return {
    kind: DRAFT_KIND,
    schema: DRAFT_SCHEMA,
    // The UI persists on each keystroke, so an intentionally blank in-progress
    // title remains a valid draft. Export can choose a display fallback.
    name: string(draft.name, 'Draft.name', { empty: true }),
    catalog,
    nodes,
    edges,
    viewport: viewport(draft.viewport, 'Draft.viewport'),
  };
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function freshId(prefix: 'node' | 'edge'): string {
  const cryptoUuid = globalThis.crypto?.randomUUID?.();
  if (cryptoUuid) return `${prefix}-${cryptoUuid}`;
  idCounter += 1;
  return `${prefix}-${Date.now().toString(36)}-${idCounter.toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function stable(value: JsonValue): JsonValue {
  if (Array.isArray(value)) return value.map(stable);
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
  }
  return value;
}

export function createEmptyDraft(catalog: Catalog): EditorDraft {
  return {
    kind: DRAFT_KIND,
    schema: DRAFT_SCHEMA,
    name: catalog.name,
    catalog: validateCatalog(clone(catalog), 'Catalog'),
    nodes: [],
    edges: [],
    viewport: { x: 0, y: 0, zoom: 1 },
  };
}

/** Convert a server-resolved project flow to a laid-out, editable draft. */
export function projectFlowDraft(catalog: Catalog, graph: ExecutionGraph, layout?: FlowLayout | null): EditorDraft {
  const layoutById = new Map((layout?.nodes ?? []).map((node) => [node.id, node]));
  const draft = validateDraft({
    ...createEmptyDraft(catalog), name: graph.name,
    nodes: graph.nodes.map((node, index) => {
      const saved = layoutById.get(node.id);
      return {
        ...node,
        label: saved?.label ?? catalog.tasks.find((task) => task.key === node.taskKey)?.taskId ?? node.id,
        notes: saved?.notes ?? '',
        position: saved?.position ?? { x: 60 + (index % 3) * 300, y: 180 + Math.floor(index / 3) * 240 },
      };
    }),
    edges: graph.edges,
    viewport: layout?.viewport ?? { x: 0, y: 0, zoom: 1 },
  });
  return draft;
}

/** Presentation information is deliberately excluded from executable flow graphs. */
export function flowLayout(draft: EditorDraft): FlowLayout {
  const current = validateDraft(draft);
  return {
    schema: 1,
    viewport: current.viewport,
    nodes: current.nodes.map(({ id, position, label, notes }) => ({ id, position, label, notes })),
  };
}

export function parseDraft(text: string): EditorDraft {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    fail('Draft import is not valid JSON');
  }
  return validateDraft(parsed);
}

export function serializeDraft(draft: EditorDraft): string {
  return `${JSON.stringify(stable(validateDraft(draft) as unknown as JsonValue))}\n`;
}

export function addTask(draft: EditorDraft, taskKey: string, position: Point = { x: 0, y: 0 }): EditorDraft {
  const current = validateDraft(draft);
  const task = current.catalog.tasks.find((item) => item.key === taskKey);
  if (!task) fail(`Unknown task key: ${taskKey}`);
  const nextPosition = point(position, 'position');
  return {
    ...current,
    nodes: [...current.nodes, {
      id: freshId('node'), taskKey, position: nextPosition,
      label: task.taskId, notes: '', parameters: {},
    }],
  };
}

export function eligibleTargetArguments(draft: EditorDraft, target: string, excludeEdgeId?: string): string[] {
  const current = validateDraft(draft);
  const node = current.nodes.find((item) => item.id === target);
  if (!node) fail('Connections must use nodes in this draft');
  const task = current.catalog.tasks.find((item) => item.key === node.taskKey);
  if (!task) return [];
  // `inputs` is descriptive metadata. Treat only simple identifiers as named
  // callable arguments; prose remains unknown rather than being guessed.
  const namedInputs = task.inputs.flatMap((input) => {
    // We accept a bare name or a simple `name: annotation` description, but
    // never attempt to turn general prose into an executable argument name.
    const match = input.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*[^,]+)?\s*$/);
    return match ? [match[1]] : [];
  });
  const supplied = new Set(current.edges.filter((edge) => edge.target === target && edge.id !== excludeEdgeId)
    .map((edge) => edge.argument).filter((argument): argument is string => Boolean(argument)));
  return namedInputs.filter((input) => !supplied.has(input) && !Object.hasOwn(node.parameters, input));
}

function suggestedArgument(draft: EditorDraft, target: string, excludeEdgeId?: string): string | undefined {
  const candidates = eligibleTargetArguments(draft, target, excludeEdgeId);
  return candidates.length === 1 ? candidates[0] : undefined;
}

function assertConnection(draft: EditorDraft, source: string, target: string): void {
  if (source === target) fail('A node cannot connect to itself');
  const ids = new Set(draft.nodes.map((node) => node.id));
  if (!ids.has(source) || !ids.has(target)) fail('Connections must use nodes in this draft');
}

function newConnectionArgument(draft: EditorDraft, source: string, target: string): string | undefined {
  assertConnection(draft, source, target);
  const argument = suggestedArgument(draft, target);
  // An existing unmapped wire must be mapped, not duplicated by the other UI path.
  if (draft.edges.some((edge) => edge.source === source && edge.target === target && (edge.argument === undefined || edge.argument === argument || argument === undefined))) fail('That connection already exists');
  return argument;
}

/** The add control and pointer wiring use the same connection eligibility rules. */
export function canConnectNodes(draft: EditorDraft, source: string, target: string): boolean {
  try { newConnectionArgument(validateDraft(draft), source, target); return true; }
  catch { return false; }
}

export function connectNodes(draft: EditorDraft, source: string, target: string): EditorDraft {
  const current = validateDraft(draft);
  const argument = newConnectionArgument(current, source, target);
  return { ...current, edges: [...current.edges, { id: freshId('edge'), source, target, ...(argument === undefined ? {} : { argument }) }] };
}

/** Reconnect a draft edge while retaining its mapping when its target is unchanged. */
export function reconnectNodes(draft: EditorDraft, id: string, source: string, target: string): EditorDraft {
  const current = validateDraft(draft);
  const existing = current.edges.find((edge) => edge.id === id);
  if (!existing) fail(`Unknown connection: ${id}`);
  assertConnection(current, source, target);
  if (existing.source === source && existing.target === target) return current;
  const argument = existing.target === target ? existing.argument : suggestedArgument(current, target, id);
  if (current.edges.some((edge) => edge.id !== id && edge.source === source && edge.target === target && edge.argument === argument)) fail('That connection already exists');
  return { ...current, edges: current.edges.map((edge) => edge.id === id ? { ...edge, source, target, ...(argument === undefined ? { argument: undefined } : { argument }) } : edge) };
}

export function setEdgeArgument(draft: EditorDraft, id: string, argument: string): EditorDraft {
  const current = validateDraft(draft);
  if (!argument.trim()) fail('Connection argument is required for execution');
  if (!current.edges.some((edge) => edge.id === id)) fail(`Unknown connection: ${id}`);
  return { ...current, edges: current.edges.map((edge) => edge.id === id ? { ...edge, argument: argument.trim() } : edge) };
}

/** Clear a draft-only mapping while retaining the visible connection. */
export function clearEdgeArgument(draft: EditorDraft, id: string): EditorDraft {
  const current = validateDraft(draft);
  if (!current.edges.some((edge) => edge.id === id)) fail(`Unknown connection: ${id}`);
  return { ...current, edges: current.edges.map((edge) => edge.id === id ? { ...edge, argument: undefined } : edge) };
}

/** Validate a draft as an executable graph without treating descriptions as types. */
export function executionGraph(draft: EditorDraft, bindings: Record<string, string>): ExecutionGraph {
  const current = validateDraft(draft);
  if (current.catalog.kind !== 'project') fail('Open a project in the editor before running a draft');
  if (!current.nodes.length) fail('Add at least one task before running this draft');
  const ids = new Set(current.nodes.map((node) => node.id));
  const keys = new Set(current.nodes.map((node) => node.taskKey));
  for (const key of keys) if (!bindings[key]) fail('This draft contains tasks that are not bound by the open project');
  const argumentsByTarget = new Set<string>();
  const pythonKeywords = new Set(['False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'try', 'while', 'with', 'yield']);
  const reservedArguments = new Set(['return_state', 'wait_for']);
  const validArgument = (value: string) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(value) && !value.startsWith('__') && !pythonKeywords.has(value) && !reservedArguments.has(value);
  for (const edge of current.edges) {
    if (!edge.argument) fail('Every connection needs a target argument before this draft can run');
    if (!validArgument(edge.argument)) fail(`Connection argument ${edge.argument} is not a valid Python argument name`);
    const key = `${edge.target}\u0000${edge.argument}`;
    if (argumentsByTarget.has(key)) fail(`More than one connection supplies ${edge.argument} on the same task`);
    const target = current.nodes.find((node) => node.id === edge.target)!;
    if (Object.hasOwn(target.parameters, edge.argument)) {
      fail(`Connection argument ${edge.argument} conflicts with a literal parameter on the same task`);
    }
    argumentsByTarget.add(key);
  }
  const downstream = new Map<string, string[]>();
  for (const id of ids) downstream.set(id, []);
  for (const edge of current.edges) downstream.get(edge.source)?.push(edge.target);
  const visiting = new Set<string>(); const visited = new Set<string>();
  const visit = (id: string) => {
    if (visiting.has(id)) fail('Executable graphs cannot contain cycles');
    if (visited.has(id)) return;
    visiting.add(id); for (const next of downstream.get(id) ?? []) visit(next); visiting.delete(id); visited.add(id);
  };
  for (const id of ids) visit(id);
  return {
    kind: 'weavem.graph', schema: current.edges.some((edge) => edge.sourcePath?.length) ? 2 : 1, name: current.name || 'Untitled flow',
    nodes: current.nodes.map(({ id, taskKey, parameters }) => ({ id, taskKey, parameters: clone(parameters) })),
    edges: current.edges.map(({ id, source, target, argument, sourcePath }) => ({ id, source, target, argument: argument!, ...(sourcePath?.length ? { sourcePath } : {}) })),
  };
}

export function removeNode(draft: EditorDraft, id: string): EditorDraft {
  const current = validateDraft(draft);
  if (!current.nodes.some((node) => node.id === id)) fail(`Unknown node: ${id}`);
  return { ...current, nodes: current.nodes.filter((node) => node.id !== id), edges: current.edges.filter((edge) => edge.source !== id && edge.target !== id) };
}

export function parseParameters(text: string): JsonObject {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    fail('Parameters must be valid JSON');
  }
  return jsonObject(parsed, 'Parameters');
}

export function loadStoredDraft(storage: Pick<Storage, 'getItem'>): { draft: EditorDraft | null; error: string | null } {
  try {
    const value = storage.getItem(STORAGE_KEY);
    if (value === null) return { draft: null, error: null };
    return { draft: parseDraft(value), error: null };
  } catch (error) {
    return { draft: null, error: `Could not load saved draft: ${error instanceof Error ? error.message : 'unknown storage error'}` };
  }
}

export function saveStoredDraft(storage: Pick<Storage, 'setItem'>, draft: EditorDraft): { error: string | null } {
  try {
    storage.setItem(STORAGE_KEY, serializeDraft(draft));
    return { error: null };
  } catch (error) {
    return { error: `Could not save draft: ${error instanceof Error ? error.message : 'unknown storage error'}` };
  }
}

/** Field selection remains a normal Python key/index path, not eval. */
export function setEdgeSourcePath(draft: EditorDraft, id: string, sourcePath: Array<string | number>): EditorDraft {
  return validateDraft({ ...draft, edges: draft.edges.map((edge) => edge.id === id ? { ...edge, sourcePath } : edge) });
}
