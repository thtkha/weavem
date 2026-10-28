import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { LAYOUT_BOUNDS, constrainedLayout, loadEditorLayout, saveEditorLayout, type EditorLayout } from './layout';
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type NodeProps,
  type ReactFlowInstance,
} from '@xyflow/react';
import {
  addTask,
  connectNodes,
  createDemoDraft,
  createEmptyDraft,
  projectFlowDraft,
  importMetadata,
  loadStoredDraft,
  parseDraft,
  parseParameters,
  removeNode,
  saveStoredDraft,
  serializeDraft,
  executionGraph,
  setEdgeArgument,
  reconnectNodes,
  clearEdgeArgument,
  eligibleTargetArguments,
} from './model';
import type { CatalogTask, DraftNode, EditorDraft, ExecutionGraph, Point, RunNodeStatus, RunState, Viewport } from './types';

type NodeData = {
  nodeId: string;
  label: string;
  task: CatalogTask;
  runStatus?: RunNodeStatus;
};

type PendingAction =
  | { kind: 'new' }
  | { kind: 'metadata'; catalogText: string }
  | { kind: 'draft'; draftText: string };

type EditorSession = { token: string; project: string; metadata: unknown; bindings: Record<string, string>; flow?: ExecutionGraph | null };

const nodeTypes = { task: TaskNode };
const defaultViewport: Viewport = { x: 0, y: 0, zoom: 1 };

type ResizeSide = 'library' | 'inspector';

function ResizeHandle({ side, width, onResize }: { side: ResizeSide; width: number; onResize: (width: number) => void }) {
  const start = useRef<{ x: number; width: number } | null>(null);
  const direction = side === 'library' ? 1 : -1;
  const label = side === 'library' ? 'Resize task library' : 'Resize inspector';
  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    start.current = { x: event.clientX, width };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!start.current) return;
    onResize(start.current.width + (event.clientX - start.current.x) * direction);
  };
  const releasePointer = (event: React.PointerEvent<HTMLDivElement>) => {
    start.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  return (
    <div
      className={`panel-resizer panel-resizer-${side}`}
      role="separator"
      aria-label={label}
      aria-orientation="vertical"
      aria-valuemin={LAYOUT_BOUNDS[side].min}
      aria-valuemax={LAYOUT_BOUNDS[side].max}
      aria-valuenow={Math.round(width)}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={releasePointer}
      onPointerCancel={releasePointer}
      onLostPointerCapture={() => { start.current = null; }}
      onKeyDown={(event) => {
        const step = event.shiftKey ? 24 : 8;
        if (event.key === 'ArrowLeft') { event.preventDefault(); onResize(width - step * direction); }
        if (event.key === 'ArrowRight') { event.preventDefault(); onResize(width + step * direction); }
        if (event.key === 'Home') { event.preventDefault(); onResize(LAYOUT_BOUNDS[side].min); }
        if (event.key === 'End') { event.preventDefault(); onResize(LAYOUT_BOUNDS[side].max); }
      }}
    />
  );
}

function TaskNode({ data, selected }: NodeProps<Node<NodeData, 'task'>>) {
  const { task } = data;
  return (
    <article
      className={`task-node ${selected ? 'is-selected' : ''}`}
      data-testid="task-node"
      data-node-id={data.nodeId}
      aria-label={`${data.label}, ${task.taskId} ${task.version}`}
    >
      <Handle
        className="node-handle node-handle-input"
        type="target"
        position={Position.Left}
        aria-label="Draft input"
      />
      <div className="node-kicker">{task.provenance} task</div>
      <strong className="node-title">{data.label}</strong>
      <code className="node-id">{task.taskId}</code>
      <div className="node-metadata">
        <span>{task.version}</span>
        <span>{task.backend}</span>
      </div>
      {data.runStatus && <span className={`node-run-status ${data.runStatus}`}>{data.runStatus}</span>}
      <div className="node-port-labels">
        <span>input</span>
        <span>output</span>
      </div>
      <Handle
        className="node-handle node-handle-output"
        type="source"
        position={Position.Right}
        aria-label="Draft output"
      />
    </article>
  );
}

function taskFor(draft: EditorDraft, node: DraftNode | undefined): CatalogTask | undefined {
  return node ? draft.catalog.tasks.find((task) => task.key === node.taskKey) : undefined;
}

const unavailableStorage: Pick<Storage, 'getItem' | 'setItem'> = {
  getItem() {
    throw new Error('Browser storage is unavailable');
  },
  setItem() {
    throw new Error('Browser storage is unavailable');
  },
};

function safeStorage(): Pick<Storage, 'getItem' | 'setItem'> {
  try {
    return window.localStorage;
  } catch {
    return unavailableStorage;
  }
}

function icon(name: 'plus' | 'folder' | 'download' | 'file' | 'play' | 'stop' | 'fullscreen' | 'fullscreenExit' | 'x') {
  const paths = {
    plus: <path d="M12 5v14M5 12h14" />,
    folder: <path d="M3 7.8A2.8 2.8 0 0 1 5.8 5H10l2 2h6.2A2.8 2.8 0 0 1 21 9.8v7.4a2.8 2.8 0 0 1-2.8 2.8H5.8A2.8 2.8 0 0 1 3 17.2Z" />,
    download: <><path d="M12 3v12" /><path d="m7 10 5 5 5-5M5 20h14" /></>,
    file: <path d="M7 3h7l4 4v14H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm6 0v5h5" />,
    play: <path d="m9 5 10 7-10 7Z" fill="currentColor" stroke="none" />,
    stop: <path d="M6 6h12v12H6Z" fill="currentColor" stroke="none" />,
    fullscreen: <path d="M8 3H3v5M16 3h5v5M21 16v5h-5M3 16v5h5" />,
    fullscreenExit: <path d="M9 3v6H3M15 3v6h6M21 15h-6v6M3 15h6v6" />,
    x: <path d="m6 6 12 12M18 6 6 18" />,
  };
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      {paths[name]}
    </svg>
  );
}

export default function App() {
  const storage = useMemo(safeStorage, []);
  const initial = useMemo(() => loadStoredDraft(storage), [storage]);
  const initialLayout = useMemo(() => loadEditorLayout(storage), [storage]);
  const [draft, setDraft] = useState<EditorDraft>(() => initial.draft ?? createDemoDraft());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [measurements, setMeasurements] = useState<Record<string, { width: number; height: number }>>({});
  const [selectedEdgeIds, setSelectedEdgeIds] = useState<Set<string>>(() => new Set());
  const [search, setSearch] = useState('');
  const [provenance, setProvenance] = useState<'all' | 'local' | 'released'>('all');
  const [status, setStatus] = useState(initial.draft ? 'Restored browser draft' : 'Demo catalog · browser only');
  const [error, setError] = useState<string | null>(initial.error);
  const [autosavePaused, setAutosavePaused] = useState(Boolean(initial.error));
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [flow, setFlow] = useState<ReactFlowInstance<Node<NodeData, 'task'>, Edge> | null>(null);
  const [parameterText, setParameterText] = useState('{}');
  const [connectTarget, setConnectTarget] = useState('');
  const [edgeArgument, setEdgeArgumentText] = useState('');
  const [session, setSession] = useState<EditorSession | null>(null);
  const [sessionMessage, setSessionMessage] = useState('Disconnected: run this editor with weavem editor --project PATH');
  const [run, setRun] = useState<RunState | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [logOpen, setLogOpen] = useState(true);
  const [layout, setLayout] = useState<EditorLayout>(initialLayout);
  const [canvasFullscreen, setCanvasFullscreen] = useState(false);
  const metadataInput = useRef<HTMLInputElement>(null);
  const draftInput = useRef<HTMLInputElement>(null);
  const canvas = useRef<HTMLElement>(null);
  const workbench = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const submittingRef = useRef(false);
  const reconnecting = useRef(new Map<string, { updated: boolean; escaped: boolean }>());
  const draftRef = useRef(draft);

  useEffect(() => { draftRef.current = draft; }, [draft]);

  const nodes = useMemo<Node<NodeData, 'task'>[]>(
    () => draft.nodes.flatMap((node) => {
      const task = taskFor(draft, node);
      return task
        ? [{
            id: node.id,
            type: 'task',
            position: node.position,
            selected: node.id === selectedId,
            measured: measurements[node.id],
            data: { nodeId: node.id, label: node.label, task, runStatus: run?.nodes[node.id]?.status },
          }]
        : [];
    }),
    [draft, measurements, run, selectedId],
  );
  const edges = useMemo<Edge[]>(
    () => draft.edges.map((edge) => ({
      ...edge,
      type: 'smoothstep',
      markerEnd: { type: MarkerType.ArrowClosed, color: '#90a96e' },
      label: edge.argument,
      selected: selectedEdgeIds.has(edge.id),
      ariaLabel: `Draft connection from ${edge.source} to ${edge.target}`,
    })),
    [draft.edges, selectedEdgeIds],
  );
  const selectedNode = draft.nodes.find((node) => node.id === selectedId);
  const selectedTask = taskFor(draft, selectedNode);
  const selectedEdge = draft.edges.find((edge) => selectedEdgeIds.has(edge.id));
  const running = run?.status === 'running';
  const executionActive = Boolean(running || submitting);
  const sessionMatchesDraft = Boolean(session && draft.catalog.kind === 'project' && draft.catalog.name === session.project);
  const visibleTasks = useMemo(() => draft.catalog.tasks.filter((task) => {
    const haystack = `${task.taskId} ${task.version} ${task.backend} ${task.provenance} ${task.description}`.toLowerCase();
    return (provenance === 'all' || task.provenance === provenance) && haystack.includes(search.trim().toLowerCase());
  }), [draft.catalog.tasks, provenance, search]);

  useEffect(() => {
    setParameterText(selectedNode ? JSON.stringify(selectedNode.parameters, null, 2) : '{}');
    setConnectTarget('');
  }, [selectedId, selectedNode?.parameters]);

  useEffect(() => {
    setEdgeArgumentText(selectedEdge?.argument ?? '');
  }, [selectedEdge?.id, selectedEdge?.argument]);

  const updatePanelWidth = useCallback((side: ResizeSide, requestedWidth: number) => {
    const availableWidth = workbench.current?.clientWidth ?? window.innerWidth;
    setLayout((current) => constrainedLayout({ ...current, [side === 'library' ? 'libraryWidth' : 'inspectorWidth']: requestedWidth }, availableWidth));
  }, []);

  useEffect(() => {
    saveEditorLayout(storage, layout);
  }, [layout, storage]);

  useEffect(() => {
    const constrainToViewport = () => {
      const availableWidth = workbench.current?.clientWidth ?? window.innerWidth;
      setLayout((current) => constrainedLayout(current, availableWidth));
    };
    constrainToViewport();
    window.addEventListener('resize', constrainToViewport);
    return () => window.removeEventListener('resize', constrainToViewport);
  }, []);

  useEffect(() => {
    const onFullscreenChange = () => setCanvasFullscreen(document.fullscreenElement === canvas.current);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && document.fullscreenElement === canvas.current) {
        void document.exitFullscreen().catch(() => undefined);
      }
    };
    document.addEventListener('fullscreenchange', onFullscreenChange);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('fullscreenchange', onFullscreenChange);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, []);

  const toggleCanvasFullscreen = useCallback(async () => {
    try {
      if (document.fullscreenElement === canvas.current) await document.exitFullscreen();
      else if (canvas.current?.requestFullscreen) await canvas.current.requestFullscreen();
      else throw new Error('Canvas fullscreen is unavailable in this browser.');
    } catch (cause) {
      setError(cause instanceof Error ? `Could not change canvas fullscreen: ${cause.message}` : 'Could not change canvas fullscreen.');
    }
  }, []);

  const runControl = (className = 'button primary') => (
    running
      ? <button className={`${className} danger`} onClick={() => void cancelRun()}>{icon('stop')} Cancel run</button>
      : <button className={className} disabled={executionActive || !sessionMatchesDraft || draft.catalog.kind === 'demo'} onClick={() => void startRun()}>{icon('play')} Run flow</button>
  );

  const requestApi = useCallback(async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
    if (!session && path !== '/api/session') throw new Error('Connect a project before running');
    const headers = new Headers(init.headers);
    if (path !== '/api/session' && session) headers.set('X-Weavem-Token', session.token);
    if (init.body) headers.set('Content-Type', 'application/json');
    const response = await fetch(path, { ...init, headers });
    const payload: unknown = await response.json().catch(() => ({}));
    if (!response.ok && payload && typeof payload === 'object' && !Array.isArray(payload) && 'error' in payload && typeof payload.error === 'string') {
      throw new Error(payload.error);
    }
    if (!response.ok || !payload || typeof payload !== 'object' || Array.isArray(payload)) {
      throw new Error(response.status === 404 ? 'The local execution bridge is unavailable. Start with weavem editor --project PATH.' : `Editor bridge request failed (${response.status})`);
    }
    return payload as T;
  }, [session]);

  const connectProject = useCallback(async () => {
    try {
      const next = await requestApi<EditorSession>('/api/session');
      if (!next.token || !next.project || !next.bindings || !next.metadata) throw new Error('The editor bridge returned an invalid session');
      setSession(next);
      setSessionMessage(`Connected to ${next.project}`);
      setRunError(null);
      // Saved project flows open only after replacement confirmation. Projects
      // without one retain the existing same-project reconnect behavior.
      if (next.flow || draft.catalog.kind !== 'project' || draft.catalog.name !== next.project) {
        const catalog = importMetadata(JSON.stringify(next.metadata));
        const opened = next.flow ? projectFlowDraft(catalog, next.flow) : createEmptyDraft(catalog);
        requestAction({ kind: 'draft', draftText: serializeDraft(opened) });
      }
    } catch (cause) {
      setSession(null);
      setSessionMessage(cause instanceof Error ? cause.message : 'Could not connect to the local project');
    }
  }, [draft.catalog.kind, draft.catalog.name, requestApi]);

  const startRun = useCallback(async () => {
    if (submittingRef.current || executionActive) return;
    if (!sessionMatchesDraft || !session) { setRunError('Connect this project and load its catalog before running.'); return; }
    try {
      if (selectedNode && JSON.stringify(parseParameters(parameterText)) !== JSON.stringify(selectedNode.parameters)) {
        throw new Error('Apply the edited parameters before running this draft');
      }
      const graph = executionGraph(draft, session.bindings);
      const hasNative = draft.nodes.some((node) => taskFor(draft, node)?.provenance === 'local' && taskFor(draft, node)?.backend === 'cython');
      if (hasNative && !window.confirm('This run contains a local Cython task. Weavem may compile it before execution. Continue?')) return;
      submittingRef.current = true;
      setSubmitting(true);
      const started = await requestApi<{ runId: string; status: RunState['status'] }>('/api/runs', { method: 'POST', body: JSON.stringify(graph) });
      setRun({ runId: started.runId, status: started.status, nodes: {}, logs: '' });
      setRunError(null); setStatus('Run started');
    } catch (cause) { setRunError(cause instanceof Error ? cause.message : String(cause)); }
    finally { submittingRef.current = false; setSubmitting(false); }
  }, [draft, executionActive, parameterText, requestApi, selectedNode, session, sessionMatchesDraft]);

  const cancelRun = useCallback(async () => {
    if (!run || run.status !== 'running') return;
    try { await requestApi(`/api/runs/${encodeURIComponent(run.runId)}/cancel`, { method: 'POST', body: '{}' }); setStatus('Cancelling run…'); }
    catch (cause) { setRunError(cause instanceof Error ? cause.message : String(cause)); }
  }, [requestApi, run]);

  useEffect(() => {
    if (!run || run.status !== 'running') return undefined;
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await requestApi<RunState>(`/api/runs/${encodeURIComponent(run.runId)}`);
        if (!cancelled) setRun(next);
      } catch (cause) { if (!cancelled) setRunError(cause instanceof Error ? cause.message : String(cause)); }
    };
    void poll();
    const timer = window.setInterval(() => { void poll(); }, 500);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [requestApi, run?.runId, run?.status]);

  useEffect(() => {
    if (!run || run.status === 'running') return;
    setStatus(`Run ${run.status}`);
    setLogOpen(true);
  }, [run?.runId, run?.status]);

  useEffect(() => {
    if (autosavePaused) return undefined;
    const timeout = window.setTimeout(() => {
      const result = saveStoredDraft(storage, draft);
      if (result.error) {
        setError(`Browser autosave paused: ${result.error}`);
        setAutosavePaused(true);
      }
    }, 260);
    return () => window.clearTimeout(timeout);
  }, [autosavePaused, draft, storage]);

  const updateDraft = useCallback(
    (next: EditorDraft, message?: string, resumeAutosave = false) => {
      if (executionActive) {
        setError('The draft is locked while a run is active. Cancel or wait for it to finish.');
        return;
      }
      setDraft(next);
      if (resumeAutosave) {
        setAutosavePaused(false);
        setError(null);
      }
      if (message) setStatus(message);
      // A run describes the exact draft submitted to the local process. Never
      // leave that result attached to a subsequently edited draft.
      setRun(null);
    },
    [executionActive],
  );

  const centerPosition = useCallback((): Point | undefined => {
    const bounds = canvas.current?.getBoundingClientRect();
    const instances = draft.nodes.length;
    const offset = { x: (instances % 4) * 250, y: Math.floor(instances / 4) * 170 };
    if (!bounds || !flow) return { x: 80 + offset.x, y: 80 + offset.y };
    const center = flow.screenToFlowPosition({ x: bounds.left + bounds.width / 2, y: bounds.top + bounds.height / 2 });
    // Offsets are flow coordinates, not screen pixels, so zoom cannot collapse
    // successive library additions onto the same task card.
    return { x: center.x + offset.x, y: center.y + offset.y };
  }, [draft.nodes, flow]);

  const addCatalogTask = useCallback((key: string, position?: Point) => {
    try {
      const next = addTask(draft, key, position ?? centerPosition());
      const added = next.nodes.at(-1);
      updateDraft(next, 'Task added to draft');
      setSelectedId(added?.id ?? null);
    } catch (cause) {
      setError(String(cause));
    }
  }, [centerPosition, draft, updateDraft]);

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    let next = draft;
    for (const change of changes) {
      if (change.type === 'dimensions' && change.dimensions) {
        const size = change.dimensions;
        setMeasurements((current) => {
          if (current[change.id]?.width === size.width && current[change.id]?.height === size.height) return current;
          return { ...current, [change.id]: size };
        });
      }
      if (change.type === 'remove') next = removeNode(next, change.id);
      if (change.type === 'position' && change.position) {
        next = {
          ...next,
          nodes: next.nodes.map((node) => (
            node.id === change.id ? { ...node, position: change.position! } : node
          )),
        };
      }
      if (change.type === 'select' && change.selected) setSelectedId(change.id);
      if (change.type === 'select' && !change.selected && selectedId === change.id) setSelectedId(null);
    }
    if (next !== draft) updateDraft(next, 'Draft updated');
  }, [draft, selectedId, updateDraft]);

  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    const removed = new Set(changes.filter((change) => change.type === 'remove').map((change) => change.id));
    const selected = new Set(selectedEdgeIds);
    for (const change of changes) {
      if (change.type === 'select') {
        if (change.selected) { selected.add(change.id); setSelectedId(null); }
        else selected.delete(change.id);
      }
      if (change.type === 'remove') selected.delete(change.id);
    }
    setSelectedEdgeIds(selected);
    if (removed.size > 0) {
      updateDraft(
        { ...draft, edges: draft.edges.filter((edge) => !removed.has(edge.id)) },
        'Connection removed',
      );
    }
  }, [draft, selectedEdgeIds, updateDraft]);

  const deleteEdge = useCallback((id: string) => {
    if (executionActive) return;
    setSelectedEdgeIds((current) => {
      const next = new Set(current);
      next.delete(id);
      return next;
    });
    const current = draftRef.current;
    updateDraft({ ...current, edges: current.edges.filter((edge) => edge.id !== id) }, 'Connection deleted');
  }, [executionActive, updateDraft]);

  const addConnection = useCallback(
    (connection: Connection | { source: string | null; target: string | null }) => {
      if (executionActive || !connection.source || !connection.target) return;
      try {
        const next = connectNodes(draft, connection.source, connection.target);
        const edge = next.edges.at(-1);
        updateDraft(next, edge?.argument ? `Connection added and mapped to ${edge.argument}` : 'Connection added; mapping required');
      } catch (cause) { setError(String(cause)); }
    }, [draft, executionActive, updateDraft],
  );

  const selectEdge = useCallback((id: string) => {
    setSelectedEdgeIds(new Set([id]));
    setSelectedId(null);
  }, []);

  const reconnectEdge = useCallback((oldEdge: Edge, connection: Connection) => {
    if (executionActive || !connection.source || !connection.target) return;
    try {
      const next = reconnectNodes(draft, oldEdge.id, connection.source, connection.target);
      reconnecting.current.set(oldEdge.id, { updated: true, escaped: false });
      updateDraft(next, oldEdge.target === connection.target ? 'Connection reconnected' : 'Connection reconnected; check mapping');
      selectEdge(oldEdge.id);
    } catch (cause) { setError(String(cause)); }
  }, [draft, executionActive, selectEdge, updateDraft]);

  const onReconnectStart = useCallback((_event: React.MouseEvent, edge: Edge) => {
    if (!executionActive) reconnecting.current.set(edge.id, { updated: false, escaped: false });
  }, [executionActive]);

  const onReconnectEnd = useCallback((event: MouseEvent | TouchEvent, edge: Edge, _handle: unknown, state: { isValid: boolean | null; toNode: unknown }) => {
    const attempt = reconnecting.current.get(edge.id);
    reconnecting.current.delete(edge.id);
    if (executionActive || !attempt || attempt.updated || attempt.escaped || state.isValid || state.toNode) return;
    // Only an actual release directly on the empty pane means disconnect.
    // Invalid handles/nodes, outside releases, Escape and pointer cancellation
    // leave the original edge untouched.
    const pointerTarget = event instanceof MouseEvent
      ? document.elementFromPoint(event.clientX, event.clientY)
      : event.target;
    if (pointerTarget instanceof Element && pointerTarget.classList.contains('react-flow__pane')) deleteEdge(edge.id);
  }, [deleteEdge, executionActive]);

  const deleteSelected = useCallback(() => {
    if (selectedEdgeIds.size > 0) {
      updateDraft(
        { ...draft, edges: draft.edges.filter((edge) => !selectedEdgeIds.has(edge.id)) },
        'Connection deleted',
      );
      setSelectedEdgeIds(new Set());
      return;
    }
    if (!selectedId) return;
    updateDraft(removeNode(draft, selectedId), 'Node and its connections deleted');
    setSelectedEdgeIds(new Set());
    setSelectedId(null);
  }, [draft, selectedEdgeIds, selectedId, updateDraft]);

  const onKeyDown = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') reconnecting.current.forEach((attempt) => { attempt.escaped = true; });
    if (pending) return;
    if (event.key === 'Delete' || event.key === 'Backspace') {
      const target = event.target as HTMLElement;
      if (!['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(target.tagName) && !target.isContentEditable) {
        event.preventDefault();
        deleteSelected();
      }
    }
  }, [deleteSelected, pending]);

  const setName = (name: string) => updateDraft({ ...draft, name });
  const updateSelected = (changes: Partial<Pick<DraftNode, 'label' | 'notes' | 'parameters'>>) => {
    if (!selectedNode) return;
    updateDraft({
      ...draft,
      nodes: draft.nodes.map((node) => (
        node.id === selectedNode.id ? { ...node, ...changes } : node
      )),
    });
  };

  useEffect(() => {
    if (!pending) {
      previousFocus.current?.focus();
      previousFocus.current = null;
      return undefined;
    }
    const focusable = () => Array.from(dialog.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled])',
    ) ?? []);
    window.requestAnimationFrame(() => focusable()[0]?.focus());
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setPending(null);
      }
      if (event.key === 'Tab') {
        const elements = focusable();
        if (elements.length === 0) return;
        const first = elements[0];
        const last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [pending]);

  const executePending = useCallback((action: PendingAction) => {
    try {
      let next: EditorDraft;
      if (action.kind === 'new') {
        next = createEmptyDraft(draft.catalog);
        updateDraft(next, 'New empty draft', true);
      } else if (action.kind === 'metadata') {
        next = createEmptyDraft(importMetadata(action.catalogText));
        updateDraft(next, 'Metadata catalog imported; new draft started', true);
      } else {
        next = parseDraft(action.draftText);
        updateDraft(next, 'Draft opened from file', true);
      }
      setSelectedId(null);
      setSelectedEdgeIds(new Set());
      window.requestAnimationFrame(() => flow?.setViewport(next.viewport));
      setPending(null);
    } catch (cause) {
      setError(String(cause));
      setPending(null);
    }
  }, [draft.catalog, flow, updateDraft]);

  const requestAction = (action: PendingAction) => {
    // Empty graphs can still contain a title, imported catalog and viewport.
    // Confirm all replacements instead of guessing whether that work matters.
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setPending(action);
  };

  const readFile = async (file: File | undefined, kind: 'metadata' | 'draft') => {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { setError('Import file must be 5 MB or smaller.'); return; }
    try {
      const text = await file.text();
      if (kind === 'metadata') importMetadata(text); else parseDraft(text);
      requestAction(kind === 'metadata' ? { kind, catalogText: text } : { kind, draftText: text });
    } catch (cause) {
      setError(`Could not import file: ${String(cause)}`);
    }
  };

  const exportDraft = () => {
    try {
      const url = URL.createObjectURL(new Blob([serializeDraft(draft)], { type: 'application/json' }));
      const anchor = document.createElement('a');
      anchor.href = url;
      const baseName = draft.name.trim().replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'weavem';
      anchor.download = `${baseName}.weavem-draft.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      setStatus('Draft JSON exported');
    } catch (cause) { setError(String(cause)); }
  };

  const applyParameters = () => {
    try { updateSelected({ parameters: parseParameters(parameterText) }); if (!autosavePaused) setError(null); setStatus('Draft parameters applied'); }
    catch (cause) { setError(String(cause)); }
  };

  return (
    <main className="app-shell" onKeyDown={onKeyDown}>
      <section className="desktop-notice" aria-label="Desktop requirement" inert={pending ? true : undefined}>
        <div>
          <strong>Weavem node editor is a desktop workbench.</strong>
          <span>Open this draft on a screen at least 1100px wide to edit it.</span>
        </div>
        <button className="button primary" onClick={exportDraft}>
          {icon('download')} Export draft
        </button>
      </section>
      <div ref={workbench} className="workbench" style={{ '--library-width': `${layout.libraryWidth}px`, '--inspector-width': `${layout.inspectorWidth}px` } as React.CSSProperties} inert={pending ? true : undefined}>
        <header className="topbar">
          <div className="topbar-main">
            <div className="brand">
              <span className="brand-mark">W</span>
              <span>weavem</span>
              <span className="prototype-badge">prototype</span>
            </div>
            <label className="draft-name">
              <span>Draft name</span>
              <input aria-label="Draft name" disabled={executionActive} value={draft.name} onChange={(event) => setName(event.target.value)} />
            </label>
          </div>
          <div className="toolbar-actions" role="group" aria-label="Draft actions">
            <button className="button" disabled={executionActive} onClick={() => requestAction({ kind: 'new' })}>
              {icon('plus')} New draft
            </button>
            <button className="button" disabled={executionActive} onClick={() => metadataInput.current?.click()}>
              {icon('file')} Import metadata
            </button>
            <button className="button" disabled={executionActive} onClick={() => draftInput.current?.click()}>
              {icon('folder')} Open draft
            </button>
            <button className="button primary" onClick={exportDraft}>
              {icon('download')} Export draft
            </button>
            <button className="button" disabled={executionActive} onClick={() => void connectProject()}>
              {session ? 'Reconnect project' : 'Connect project'}
            </button>
            {run && <button className="button" aria-pressed={logOpen} onClick={() => setLogOpen((open) => !open)}>{logOpen ? 'Hide run log' : 'Show run log'}</button>}
            <div className="run-actions">{runControl()}</div>
          </div>
          <div className="save-state" role="status">
            <span className={autosavePaused ? 'status-dot warning' : 'status-dot'} />
            {autosavePaused ? 'Autosave paused' : status}
          </div>
          <input
            ref={metadataInput}
            className="visually-hidden"
            aria-label="Import metadata JSON"
            type="file"
            accept="application/json,.json"
            onChange={(event) => {
              void readFile(event.currentTarget.files?.[0], 'metadata');
              event.currentTarget.value = '';
            }}
          />
          <input
            ref={draftInput}
            className="visually-hidden"
            aria-label="Open draft JSON"
            type="file"
            accept="application/json,.json"
            onChange={(event) => {
              void readFile(event.currentTarget.files?.[0], 'draft');
              event.currentTarget.value = '';
            }}
          />
        </header>

        <aside className="library panel" aria-label="Task library">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Task library</p>
              <h1>{draft.catalog.name}</h1>
            </div>
            <span className={`catalog-badge ${draft.catalog.kind}`}>
              {draft.catalog.kind === 'demo' ? 'Sample catalog' : 'Project metadata'}
            </span>
          </div>
          <p className="library-count">{draft.catalog.tasks.length} task{draft.catalog.tasks.length === 1 ? '' : 's'} · descriptive metadata</p>
          <label className="search">
            <span>Search tasks</span>
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="ID, version, backend…" />
          </label>
          <div className="filters" aria-label="Task provenance filter">
            {(['all', 'local', 'released'] as const).map((filter) => (
              <button
                key={filter}
                className={provenance === filter ? 'active' : ''}
                aria-pressed={provenance === filter}
                onClick={() => setProvenance(filter)}
              >
                {filter === 'all' ? 'All' : filter}
              </button>
            ))}
          </div>
          <div className="task-list">
            {visibleTasks.map((task) => (
              <article
                className="library-task"
                key={task.key}
                draggable
                onDragStart={(event) => {
                  event.dataTransfer.setData('application/weavem-task', task.key);
                  event.dataTransfer.effectAllowed = 'copy';
                }}
              >
                <div className="task-card-top">
                  <code>{task.taskId}</code>
                  <span className={`provenance ${task.provenance}`}>{task.provenance}</span>
                </div>
                {sessionMatchesDraft && !session?.bindings[task.key] && <p className="field-help" role="note">Unbound in this project: you can compose with it, but bind it before running.</p>}
                <p>{task.description || 'No description supplied.'}</p>
                <div className="task-tags">
                  <span>{task.version}</span>
                  <span>{task.backend}</span>
                </div>
                <button className="add-task" disabled={executionActive} aria-label={`Add task ${task.taskId}`} onClick={() => addCatalogTask(task.key)}>
                  {icon('plus')} Add task
                </button>
              </article>
            ))}
            {visibleTasks.length === 0 && <p className="empty-list">No tasks match this search.</p>}
          </div>
        </aside>
        <ResizeHandle side="library" width={layout.libraryWidth} onResize={(width) => updatePanelWidth('library', width)} />

        <section
          ref={canvas}
          className="canvas-area"
          aria-label="Draft canvas"
          onDrop={(event) => {
            event.preventDefault();
            const key = event.dataTransfer.getData('application/weavem-task');
            if (key) addCatalogTask(key, flow?.screenToFlowPosition({ x: event.clientX, y: event.clientY }));
          }}
          onDragOver={(event) => event.preventDefault()}
        >
          <div className="canvas-header">
            <div>
              <span className="eyebrow">Composition draft</span>
              <span className="canvas-summary">{draft.nodes.length} nodes · {draft.edges.length} connections</span>
            </div>
            {canvasFullscreen && <div className="canvas-run-action">
              {runControl()}
              {run && <button className="button" aria-pressed={logOpen} onClick={() => setLogOpen((open) => !open)}>{logOpen ? 'Hide run log' : 'Show run log'}</button>}
              <span className="fullscreen-status" role="status">{error || runError || (run ? `Run ${run.status}` : sessionMessage)}</span>
            </div>}
            <button
              className="icon-button"
              aria-label={canvasFullscreen ? 'Exit canvas fullscreen' : 'Enter canvas fullscreen'}
              title={canvasFullscreen ? 'Exit canvas fullscreen' : 'Enter canvas fullscreen'}
              onClick={() => void toggleCanvasFullscreen()}
            >
              {icon(canvasFullscreen ? 'fullscreenExit' : 'fullscreen')}
            </button>
          </div>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView={!initial.draft}
            onInit={(instance) => {
              setFlow(instance);
              instance.setViewport(draft.viewport);
            }}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={addConnection}
            edgesReconnectable={!executionActive}
            onReconnectStart={onReconnectStart}
            onReconnect={reconnectEdge}
            onReconnectEnd={onReconnectEnd}
            onPointerCancelCapture={() => reconnecting.current.forEach((attempt) => { attempt.escaped = true; })}
            nodesDraggable={!executionActive}
            nodesConnectable={!executionActive}
            elementsSelectable={!executionActive}
            onNodeClick={(_, node) => {
              setSelectedId(node.id);
              setSelectedEdgeIds(new Set());
            }}
            onEdgeClick={(_, edge) => {
              selectEdge(edge.id);
            }}
            onPaneClick={() => {
              setSelectedId(null);
              setSelectedEdgeIds(new Set());
            }}
            onMoveEnd={(_, viewport) => setDraft((current) => ({ ...current, viewport }))}
            defaultViewport={draft.viewport ?? defaultViewport}
            deleteKeyCode={null}
            multiSelectionKeyCode={['Meta', 'Control']}
            aria-label="Weavem draft graph"
          >
            <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="#374227" />
            <Controls showInteractive={false} />
            <MiniMap
              nodeColor={(node) => (node.data as NodeData).task?.provenance === 'released' ? '#8197ef' : '#90a96e'}
              maskColor="rgba(16, 20, 12, .7)"
            />
          </ReactFlow>
          {draft.nodes.length === 0 && (
            <div className="canvas-empty">
              <span className="empty-mark">+</span>
              <strong>Start a composition draft</strong>
              <p>Add a task from the library, or drag one onto this canvas.</p>
            </div>
          )}
          <div className="canvas-footer">{executionActive ? `Run ${run?.runId ?? 'submission'} is active; editing is locked` : sessionMatchesDraft ? 'Ready to run · connections require target argument mapping' : 'Draft wiring · connect a local project to run'}</div>
          {run && logOpen && <section className="run-log panel" aria-label="Run log"><div className="panel-heading"><div><p className="eyebrow">Local run</p><h2>{run.status}</h2></div><button className="icon-button" aria-label="Hide run log" onClick={() => setLogOpen(false)}>{icon('x')}</button></div><code>{run.runId}</code><pre>{run.logs || 'Waiting for task output…'}</pre>{run.error && <p role="alert">{run.error}</p>}</section>}
        </section>
        <ResizeHandle side="inspector" width={layout.inspectorWidth} onResize={(width) => updatePanelWidth('inspector', width)} />

        <aside className="inspector panel" aria-label="Node inspector">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Inspector</p>
              <h2>{selectedNode ? 'Task instance' : 'Nothing selected'}</h2>
            </div>
            {selectedNode && (
              <button className="icon-button" disabled={executionActive} aria-label="Delete selected node" title="Delete node" onClick={deleteSelected}>
                {icon('x')}
              </button>
            )}
          </div>
          {selectedNode && selectedTask ? <div className="inspector-content">
            <section className="task-overview">
              <div className="inspector-label">Referenced task</div>
              <code>{selectedTask.taskId}</code>
              <div className="task-tags">
                <span>{selectedTask.version}</span>
                <span>{selectedTask.backend}</span>
                <span className={`provenance ${selectedTask.provenance}`}>{selectedTask.provenance}</span>
              </div>
            </section>
            <dl className="metadata-list">
              <div><dt>Inputs</dt><dd>{selectedTask.inputs.length ? selectedTask.inputs.join(', ') : 'None declared'}</dd></div>
              <div><dt>Output</dt><dd>{selectedTask.output || 'None declared'}</dd></div>
              <div><dt>Source</dt><dd className="mono-break">{selectedTask.source}</dd></div>
              {selectedTask.manifestSha256 && <div><dt>Manifest hash</dt><dd className="mono-break">{selectedTask.manifestSha256}</dd></div>}
            </dl>
            <label className="field">
              <span>Node label</span>
              <input disabled={executionActive} value={selectedNode.label} onChange={(event) => updateSelected({ label: event.target.value })} />
            </label>
            <label className="field">
              <span>Notes</span>
              <textarea disabled={executionActive} value={selectedNode.notes} onChange={(event) => updateSelected({ notes: event.target.value })} placeholder="Private drafting note" />
            </label>
            <label className="field">
              <span>Draft parameters</span>
              <textarea
                className="code-area"
                value={parameterText}
                disabled={executionActive}
                onChange={(event) => setParameterText(event.target.value)}
                spellCheck={false}
                aria-describedby="parameter-help"
              />
            </label>
            <p id="parameter-help" className="field-help">JSON object saved only in this editor draft.</p>
            <button className="button secondary wide" disabled={executionActive} onClick={applyParameters}>Apply parameters</button>
            <section className="connection-editor">
              <h3>Add connection</h3>
              <select aria-label="Add connection target" disabled={executionActive} value={connectTarget} onChange={(event) => setConnectTarget(event.target.value)}>
                <option value="" disabled>Select a draft node</option>
                {draft.nodes.filter((node) => node.id !== selectedNode.id).map((node) => <option key={node.id} value={node.id}>{node.label}</option>)}
              </select>
              <button className="button secondary wide" onClick={() => { if (connectTarget) { addConnection({ source: selectedNode.id, target: connectTarget }); setConnectTarget(''); } }} disabled={!connectTarget || executionActive}>Add connection</button>
            </section>
            {(['incoming', 'outgoing'] as const).map((direction) => {
              const connected = draft.edges.filter((edge) => direction === 'incoming' ? edge.target === selectedNode.id : edge.source === selectedNode.id);
              return <section className="outgoing" key={direction}>
                <h3>{direction === 'incoming' ? 'Incoming connections' : 'Outgoing connections'}</h3>
                {connected.length ? connected.map((edge) => {
                  const otherId = direction === 'incoming' ? edge.source : edge.target;
                  const otherLabel = draft.nodes.find((node) => node.id === otherId)?.label ?? otherId;
                  return <div className="connection-row" key={`${edge.id}:${edge.argument ?? ''}`}>
                    <button type="button" disabled={executionActive} onClick={() => selectEdge(edge.id)} aria-label={`Select connection ${direction === 'incoming' ? 'from' : 'to'} ${otherLabel}`}><span>{direction === 'incoming' ? '←' : '→'} {otherLabel}</span><small>{edge.argument ?? 'Mapping required'}</small></button>
                    <input aria-label={`Connection target argument to ${otherLabel}`} list={`connection-arguments-${edge.id}`} disabled={executionActive} defaultValue={edge.argument ?? ''} placeholder="Mapping required" onBlur={(event) => {
                      const value = event.currentTarget.value.trim();
                      if (value === (edge.argument ?? '')) return;
                      try {
                        updateDraft(value ? setEdgeArgument(draft, edge.id, value) : clearEdgeArgument(draft, edge.id), value ? 'Connection argument mapped' : 'Connection mapping cleared');
                      } catch (cause) { setError(String(cause)); }
                    }} />
                    <datalist id={`connection-arguments-${edge.id}`}>
                      {eligibleTargetArguments(draft, edge.target, edge.id).map((argument) => <option key={argument} value={argument} />)}
                    </datalist>
                    <button type="button" disabled={executionActive} className="connection-delete" aria-label={`Delete connection to ${otherLabel}`} onClick={() => deleteEdge(edge.id)}>Delete</button>
                  </div>;
                }) : <p>No {direction} draft connections.</p>}
              </section>;
            })}
            {run?.nodes[selectedNode.id] && <section className="run-result"><h3>Run result</h3><p><strong>{run.nodes[selectedNode.id].status}</strong></p>{run.nodes[selectedNode.id].preview && <pre>{run.nodes[selectedNode.id].preview}</pre>}{run.nodes[selectedNode.id].error && <p role="alert">{run.nodes[selectedNode.id].error}</p>}</section>}
            <button className="delete-button" disabled={executionActive} onClick={deleteSelected}>Delete node</button>
          </div> : selectedEdge ? <div className="inspector-content"><section className="connection-editor"><p className="eyebrow">Connection mapping</p><h3>Target argument</h3><p className="field-help">Pass this connection’s whole result to a named argument on the target task.</p><label className="field"><span>Argument</span><input aria-label="Connection target argument" disabled={executionActive} value={edgeArgument} placeholder="for example: text" onChange={(event) => setEdgeArgumentText(event.target.value)} /></label><button className="button secondary wide" disabled={executionActive || !edgeArgument.trim()} onClick={() => { try { updateDraft(setEdgeArgument(draft, selectedEdge.id, edgeArgument), 'Connection argument mapped'); } catch (cause) { setError(String(cause)); } }}>Apply mapping</button><button className="delete-button" disabled={executionActive} onClick={() => deleteEdge(selectedEdge.id)}>Delete connection</button></section></div> : <div className="inspector-empty"><span className="empty-mark">↖</span><p>Select a task node to view descriptive metadata and edit this draft instance.</p><small>Connections need explicit argument mappings before a run.</small></div>}
        </aside>
        <footer className="bottom-status">
          <span>{error || runError ? 'Attention needed' : sessionMessage}</span>
          {error || runError ? <span role="alert">{error ?? runError}</span> : <span>{run ? `Run ${run.status}. ${run.error ?? ''}` : 'Autosaved locally in this browser. Export a file to move the draft.'}</span>}
        </footer>
      </div>

      {pending && <div className="modal-backdrop" role="presentation"><section ref={dialog} className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="replace-title"><p className="eyebrow">Replace current draft?</p><h2 id="replace-title">Your current graph will be replaced.</h2><p>Export it first if you need a portable copy. Invalid files never change the current draft.</p><div className="dialog-actions"><button className="button" onClick={() => setPending(null)}>Cancel</button><button className="button primary" onClick={() => executePending(pending)}>Replace draft</button></div></section></div>}
    </main>
  );
}
