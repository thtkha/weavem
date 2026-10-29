/** Editor-only data. These types are deliberately independent of React Flow. */
export type JsonValue = null | boolean | number | string | JsonValue[] | JsonObject;
export type JsonObject = { [key: string]: JsonValue };
export type Point = { x: number; y: number };
export type Viewport = Point & { zoom: number };

export interface CatalogTask {
  key: string;
  taskId: string;
  version: string;
  backend: 'python' | 'cython';
  provenance: 'local' | 'released';
  description: string;
  inputs: string[];
  output: string;
  source: string;
  manifestSha256?: string;
}

export interface Catalog {
  name: string;
  kind: 'demo' | 'project';
  tasks: CatalogTask[];
}

export interface DraftNode {
  id: string;
  taskKey: string;
  position: Point;
  label: string;
  notes: string;
  parameters: JsonObject;
}

export interface DraftEdge {
  id: string;
  source: string;
  target: string;
  /** The target callable argument receiving the source result. Undefined is a legacy draft wire. */
  argument?: string;
}

export interface EditorDraft {
  kind: 'weavem.editor-draft';
  schema: 2;
  name: string;
  catalog: Catalog;
  nodes: DraftNode[];
  edges: DraftEdge[];
  viewport: Viewport;
}

export interface FlowLayout {
  schema: 1;
  viewport: Viewport;
  nodes: Array<{ id: string; position: Point; label?: string; notes?: string }> ;
}

export interface FlowSummary {
  name: string;
  revision: string;
  editable: boolean;
  reason?: string;
}

export interface ProjectFlow extends FlowSummary {
  graph: ExecutionGraph | null;
  layout?: FlowLayout | null;
  source?: string;
  layoutError?: string;
}

export interface ExecutionGraph {
  kind: 'weavem.graph';
  schema: 1;
  name: string;
  nodes: Array<{ id: string; taskKey: string; parameters: JsonObject }>;
  edges: Array<{ id: string; source: string; target: string; argument: string }>;
}

export type ParameterKind = 'string' | 'number' | 'boolean' | 'json';
export interface ParameterHint {
  name: string;
  kind: ParameterKind;
  required: boolean;
  hasDefault: boolean;
  annotation?: string;
  defaultValue?: JsonValue;
  defaultDisplay?: string;
  description?: string;
}
export interface TaskParameterHints {
  origin: 'source' | 'metadata';
  parameters: ParameterHint[];
}

export type RunNodeStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
export interface RunNode { status: RunNodeStatus; preview?: string; error?: string }
export interface RunState {
  runId: string;
  status: 'running' | 'completed' | 'failed' | 'cancelled';
  flowName?: string;
  revision?: string;
  result?: string;
  phase?: 'preparing' | 'running';
  message?: string;
  nodes: Record<string, RunNode>;
  logs: string;
  error?: string;
}
