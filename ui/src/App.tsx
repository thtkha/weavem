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
  canConnectNodes,
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
  flowLayout,
  setEdgeArgument,
  setEdgeSourcePath,
  reconnectNodes,
  clearEdgeArgument,
  eligibleTargetArguments,
} from './model';
import type { CatalogTask, DraftNode, EditorDraft, ExecutionGraph, FlowLayout, FlowSummary, ProjectFlow, Point, RunNodeStatus, RunState, Viewport } from './types';
import type { TaskParameterHints } from './types';
import { ParameterEditor } from './ParameterEditor';
import { Button } from './components/Button';
import { Field } from './components/Field';
import { FieldMapping } from './FieldMapping';
import { ResultViewer } from './ResultViewer';
import { createDraftHistory, commitDraft, undoDraft, redoDraft, canUndo, canRedo, copySelection, pasteSelection, type DraftClipboard } from './editorHistory';
import { RunInspection, type RunInspectionRecord } from './RunInspection';
import { EditorToolbar } from './components/EditorToolbar';

type NodeData = {
  nodeId: string;
  label: string;
  task: CatalogTask;
  runStatus?: RunNodeStatus;
};

type PendingAction =
  | { kind: 'new' }
  | { kind: 'metadata'; catalogText: string }
  | { kind: 'draft'; draftText: string }
  | { kind: 'flow'; name: string }
  | { kind: 'attach'; session: EditorSession; runId: string };

type EditorSession = { environment?: { pythonExecutable: string; pythonVersion: string; weavemVersion: string }; token: string; project: string; metadata: unknown; bindings: Record<string, string>; parameterHints?: Record<string, TaskParameterHints>; flows?: FlowSummary[]; activeRunId?: string | null; flow?: ExecutionGraph | null };
type LoadedFlow = { name: string; revision: string | null; editable: boolean; reason?: string; source?: string };
type SavedFlowResponse = Partial<ProjectFlow> & { name: string; revision: string; editable?: boolean; reason?: string };

const nodeTypes = { task: TaskNode };
const defaultViewport: Viewport = { x: 0, y: 0, zoom: 1 };

function normalizedFlowLayout(value: unknown): FlowLayout | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const layout = value as { schema?: unknown; viewport?: unknown; nodes?: unknown };
  if (layout.schema !== 1 || !layout.viewport || typeof layout.viewport !== 'object') return null;
  const nodes = Array.isArray(layout.nodes)
    ? layout.nodes
    : layout.nodes && typeof layout.nodes === 'object'
      ? Object.entries(layout.nodes as Record<string, unknown>).map(([id, node]) => ({ id, ...(node as object) }))
      : [];
  const validNodes = nodes.filter((node): node is { id: string; position: Point; label?: string; notes?: string } => {
    if (!node || typeof node !== 'object') return false;
    const candidate = node as { id?: unknown; position?: { x?: unknown; y?: unknown }; label?: unknown; notes?: unknown };
    return typeof candidate.id === 'string' && typeof candidate.position?.x === 'number' && typeof candidate.position?.y === 'number'
      && (candidate.label === undefined || typeof candidate.label === 'string') && (candidate.notes === undefined || typeof candidate.notes === 'string');
  });
  const viewport = layout.viewport as { x?: unknown; y?: unknown; zoom?: unknown };
  if (typeof viewport.x !== 'number' || typeof viewport.y !== 'number' || typeof viewport.zoom !== 'number' || viewport.zoom <= 0) return null;
  return { schema: 1, viewport: { x: viewport.x, y: viewport.y, zoom: viewport.zoom }, nodes: validNodes };
}

type ResizeSide = 'library' | 'inspector';
type InspectorSectionName = 'parameters' | 'connections' | 'result' | 'details';
type InspectorSections = Record<InspectorSectionName, boolean>;

function InspectorSection({
  name,
  title,
  open,
  onToggle,
  children,
}: {
  name: InspectorSectionName;
  title: string;
  open: boolean;
  onToggle: (name: InspectorSectionName, open: boolean) => void;
  children: React.ReactNode;
}) {
  return (
    <details
      className="inspector-section"
      open={open}
      onToggle={(event) => onToggle(name, event.currentTarget.open)}
    >
      <summary>{title}</summary>
      <div className="inspector-section-content">{children}</div>
    </details>
  );
}

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
        title="Input: connect an upstream task"
      />
      <strong className="node-title">{data.label}</strong>
      <code className="node-id">{task.taskId}</code>
      <div className="node-metadata">
        <span>{task.provenance}</span>
        <span>{task.version}</span>
        <span>{task.backend}</span>
      </div>
      {data.runStatus && <span className={`node-run-status ${data.runStatus}`}>{data.runStatus}</span>}
      <Handle
        className="node-handle node-handle-output"
        type="source"
        position={Position.Right}
        aria-label="Draft output"
        title="Output: connect a downstream task"
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
  const [draft, setDraft] = useState<EditorDraft>(() => initial.draft ?? { ...createEmptyDraft({ name: 'No project connected', kind: 'project', tasks: [] }), name: 'new_flow' });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [measurements, setMeasurements] = useState<Record<string, { width: number; height: number }>>({});
  const [selectedEdgeIds, setSelectedEdgeIds] = useState<Set<string>>(() => new Set());
  const [search, setSearch] = useState('');
  const [provenance, setProvenance] = useState<'all' | 'local' | 'released'>('all');
  const [status, setStatus] = useState(initial.draft ? 'Restored browser draft' : 'Connecting to project…');
  const [error, setError] = useState<string | null>(initial.error);
  const [autosavePaused, setAutosavePaused] = useState(Boolean(initial.error));
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [flow, setFlow] = useState<ReactFlowInstance<Node<NodeData, 'task'>, Edge> | null>(null);
  const [parameterText, setParameterText] = useState('{}');
  const [parameterPending, setParameterPending] = useState(false);
  const [connectTarget, setConnectTarget] = useState('');
  const [connectionAdderOpen, setConnectionAdderOpen] = useState(false);
  const [edgeArgument, setEdgeArgumentText] = useState('');
  const [session, setSession] = useState<EditorSession | null>(null);
  const [sessionMessage, setSessionMessage] = useState('Start the editor with weavem editor --project PATH.');
  const [connectionPhase, setConnectionPhase] = useState<'loading' | 'connected' | 'failed'>('loading');
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [run, setRun] = useState<RunState | null>(null);
  const [sampleRun, setSampleRun] = useState<RunState | null>(null);
  const [loadedFlow, setLoadedFlow] = useState<LoadedFlow | null>(null);
  const [flowSummaries, setFlowSummaries] = useState<FlowSummary[]>([]);
  const [dirty, setDirty] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [runParametersText, setRunParametersText] = useState('{}');
  const [activeRunToAttach, setActiveRunToAttach] = useState<string | null>(null);
  const [saveAsOpen, setSaveAsOpen] = useState(false);
  const [saveAsName, setSaveAsName] = useState('');
  const [saveAsError, setSaveAsError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [logOpen, setLogOpen] = useState(true);
  const [layout, setLayout] = useState<EditorLayout>(initialLayout);
  const [canvasFullscreen, setCanvasFullscreen] = useState(false);
  const [inspectorSections, setInspectorSections] = useState<InspectorSections>({
    parameters: true,
    connections: true,
    result: true,
    details: false,
  });
  const metadataInput = useRef<HTMLInputElement>(null);
  const draftInput = useRef<HTMLInputElement>(null);
  const canvas = useRef<HTMLElement>(null);
  const workbench = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const submittingRef = useRef(false);
  const reconnecting = useRef(new Map<string, { updated: boolean; escaped: boolean }>());
  const draftRef = useRef(draft);
  const history = useRef(createDraftHistory(draft));
  const editGroup = useRef<string | null>(null);
  const clipboard = useRef<DraftClipboard | null>(null);
  const [, refreshHistory] = useState(0);
  const [selectedNodeIds, setSelectedNodeIds] = useState(new Set<string>());
  const [inspection, setInspection] = useState<RunInspectionRecord | null>(null);
  const [inspectRun, setInspectRun] = useState(false);
  const resultAutoOpenedFor = useRef<string | null>(null);
  const revisionMismatchedRun = useRef<string | null>(null);
  const sessionRef = useRef<EditorSession | null>(null);
  const connectionAttempt = useRef(0);
  const untouchedStartup = useRef(!initial.draft && !initial.error);

  useEffect(() => { sessionRef.current = session; }, [session]);

  const requestAction = useCallback((action: PendingAction) => {
    // Even an empty restored/imported graph can represent meaningful work.
    untouchedStartup.current = false;
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setPending(action);
  }, []);

  useEffect(() => { draftRef.current = draft; }, [draft]);

  useEffect(() => { if (run) setSampleRun(run); }, [run]);

  const onSelectionChange = useCallback(({ nodes: selected }: { nodes: Array<{ id: string }> }) => {
    const next = new Set(selected.map((node) => node.id));
    setSelectedNodeIds((current) => current.size === next.size && [...current].every((id) => next.has(id)) ? current : next);
  }, []);

  const nodes = useMemo<Node<NodeData, 'task'>[]>(
    () => draft.nodes.flatMap((node) => {
      const task = draft.catalog.tasks.find((task) => task.key === node.taskKey);
      return task
        ? [{
            id: node.id,
            type: 'task',
            position: node.position,
            selected: selectedNodeIds.has(node.id) || node.id === selectedId,
            measured: measurements[node.id],
            data: { nodeId: node.id, label: node.label, task, runStatus: run?.nodes[node.id]?.status },
          }]
        : [];
    }),
    // Viewport-only updates must not replace nodes during initial port measurement.
    [draft.nodes, draft.catalog.tasks, measurements, run, selectedId, selectedNodeIds],
  );
  const edges = useMemo<Edge[]>(
    () => draft.edges.map((edge) => ({
      ...edge,
      type: 'smoothstep',
      markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--color-accent)' },
      selected: selectedEdgeIds.has(edge.id),
      ariaLabel: `Draft connection from ${edge.source} to ${edge.target}`,
    })),
    [draft.edges, selectedEdgeIds],
  );
  const selectedNode = draft.nodes.find((node) => node.id === selectedId);
  const selectedTask = taskFor(draft, selectedNode);
  const selectedRunResult = selectedNode ? run?.nodes[selectedNode.id] : undefined;
  const selectedResultKey = selectedRunResult && selectedNode && run ? `${run.runId}:${selectedNode.id}` : null;
  const wiredParameters = useMemo(() => {
    if (!selectedNode) return {} as Record<string, string>;
    return Object.fromEntries(draft.edges.filter((edge) => edge.target === selectedNode.id && edge.argument)
      .map((edge) => [edge.argument!, draft.nodes.find((node) => node.id === edge.source)?.label ?? edge.source]));
  }, [draft.edges, draft.nodes, selectedNode]);
  const selectedEdge = draft.edges.find((edge) => selectedEdgeIds.has(edge.id));
  const selectedEdgeSource = selectedEdge ? draft.nodes.find((node) => node.id === selectedEdge.source) : undefined;
  const selectedEdgeTarget = selectedEdge ? draft.nodes.find((node) => node.id === selectedEdge.target) : undefined;
  const connectionTargets = selectedNode ? draft.nodes.filter((node) => node.id !== selectedNode.id).map((node) => ({
    node,
    connected: draft.edges.some((edge) => edge.source === selectedNode.id && edge.target === node.id),
    available: canConnectNodes(draft, selectedNode.id, node.id),
  })) : [];
  const targetAvailable = connectionTargets.some(({ node, available }) => node.id === connectTarget && available);
  const running = run?.status === 'running';
  const executionActive = Boolean(running || submitting);
  const sessionMatchesDraft = Boolean(session && draft.catalog.kind === 'project' && draft.catalog.name === session.project);
  const visualEditingAllowed = Boolean(sessionMatchesDraft && (loadedFlow === null || loadedFlow.editable));
  // Restored/imported browser drafts remain recoverable visual-only authoring.
  // Only a loaded Python flow explicitly marked source-only is read-only.
  const canvasEditingAllowed = !executionActive && loadedFlow?.editable !== false;
  const visibleTasks = useMemo(() => draft.catalog.tasks.filter((task) => {
    const haystack = `${task.taskId} ${task.version} ${task.backend} ${task.provenance} ${task.description}`.toLowerCase();
    return (provenance === 'all' || task.provenance === provenance) && haystack.includes(search.trim().toLowerCase());
  }), [draft.catalog.tasks, provenance, search]);

  useEffect(() => {
    setParameterText(selectedNode ? JSON.stringify(selectedNode.parameters, null, 2) : '{}');
    setParameterPending(false);
  }, [selectedId, selectedNode?.parameters]);

  useEffect(() => {
    setConnectTarget('');
    setConnectionAdderOpen(false);
  }, [selectedId]);

  useEffect(() => {
    if (connectTarget && !targetAvailable) setConnectTarget('');
  }, [connectTarget, targetAvailable]);

  useEffect(() => {
    setEdgeArgumentText(selectedEdge?.argument ?? '');
  }, [selectedEdge?.id, selectedEdge?.argument]);

  useEffect(() => {
    if (!selectedResultKey) {
      resultAutoOpenedFor.current = null;
      return;
    }
    if (resultAutoOpenedFor.current !== selectedResultKey) {
      resultAutoOpenedFor.current = selectedResultKey;
      setInspectorSections((current) => ({ ...current, result: true }));
    }
  }, [selectedResultKey]);

  const toggleInspectorSection = useCallback((name: InspectorSectionName, open: boolean) => {
    setInspectorSections((current) => current[name] === open ? current : { ...current, [name]: open });
  }, []);

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

  const runControl = () => (
    running
      ? <Button variant="danger" onClick={() => void cancelRun()}>{icon('stop')} Cancel run</Button>
      : <Button variant="primary" disabled={executionActive || !sessionMatchesDraft || draft.catalog.kind === 'demo'} onClick={() => void startRun()}>{icon('play')} Run flow</Button>
  );

  const requestApi = useCallback(async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
    const currentSession = sessionRef.current;
    if (!currentSession && path !== '/api/session') throw new Error('Connect a project before running');
    const headers = new Headers(init.headers);
    if (path !== '/api/session' && currentSession) headers.set('X-Weavem-Token', currentSession.token);
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
  }, []);

  const applyOpenedFlow = useCallback((catalog: ReturnType<typeof importMetadata>, opened: ProjectFlow) => {
    if (!opened.graph) throw new Error(opened.reason ?? 'This flow cannot be displayed as a complete editable graph.');
    const next = projectFlowDraft(catalog, opened.graph, normalizedFlowLayout(opened.layout));
    setDraft(next);
    history.current = createDraftHistory(next); editGroup.current = null; setRun(null); setSampleRun(null);
    setLoadedFlow({ name: opened.name, revision: opened.revision, editable: opened.editable, reason: opened.reason, source: opened.source });
    setDirty(false);
    setSelectedId(null);
    setSelectedNodeIds(new Set());
    setSelectedEdgeIds(new Set());
    window.requestAnimationFrame(() => flow?.setViewport(next.viewport));
  }, [flow]);

  const loadFlow = useCallback(async (name: string, { replace = true }: { replace?: boolean } = {}) => {
    if (!session) throw new Error('Connect a project before opening a flow');
    const encoded = encodeURIComponent(name);
    const opened = await requestApi<ProjectFlow>(`/api/flows/${encoded}`);
    const catalog = importMetadata(JSON.stringify(session.metadata));
    if (!opened.graph) {
      const sourceDraft = { ...createEmptyDraft(catalog), name: opened.name };
      setDraft(sourceDraft); history.current = createDraftHistory(sourceDraft); editGroup.current = null; setRun(null); setSampleRun(null);
      setLoadedFlow({ name: opened.name, revision: opened.revision, editable: false, reason: opened.reason, source: opened.source });
      setDirty(false); setSelectedId(null); setSelectedNodeIds(new Set()); setSelectedEdgeIds(new Set());
      setStatus(`Opened ${opened.name}: visual editing is unavailable`);
      return { name: opened.name, revision: opened.revision, editable: false, reason: opened.reason, source: opened.source } satisfies LoadedFlow;
    }
    if (replace) applyOpenedFlow(catalog, opened);
    setStatus(opened.layoutError ? `Opened flow ${opened.name}; layout was reset: ${opened.layoutError}` : `Opened flow ${opened.name}`);
    return { name: opened.name, revision: opened.revision, editable: opened.editable, reason: opened.reason, source: opened.source } satisfies LoadedFlow;
  }, [applyOpenedFlow, requestApi, session]);

  const connectProject = useCallback(async (automatic = false, externalSignal?: AbortSignal) => {
    const attempt = ++connectionAttempt.current;
    const controller = new AbortController();
    const abort = () => controller.abort();
    externalSignal?.addEventListener('abort', abort, { once: true });
    const timeout = window.setTimeout(abort, 10_000);
    setConnectionPhase('loading'); setConnectionError(null);
    try {
      const next = await requestApi<EditorSession>('/api/session', { signal: controller.signal });
      if (externalSignal?.aborted || attempt !== connectionAttempt.current) return;
      // An aborted body read can be recovered by requestApi's JSON fallback.
      if (controller.signal.aborted) throw new Error('Session request timed out');
      if (!next.token || !next.project || !next.bindings || !next.metadata) throw new Error('The editor bridge returned an invalid session');
      const catalog = importMetadata(JSON.stringify(next.metadata));
      // An existing run can replace the visible source only after explicit consent.
      if (next.activeRunId) {
        setConnectionPhase('connected');
        requestAction({ kind: 'attach', session: next, runId: next.activeRunId });
        return;
      }
      sessionRef.current = next;
      setSession(next); setFlowSummaries(next.flows ?? []);
      setSessionMessage(`Connected to ${next.project}`);
      setRunError(null); setConnectionPhase('connected');
      const current = draftRef.current;
      const changingProject = current.catalog.kind !== 'project' || current.catalog.name !== next.project;
      if (automatic && untouchedStartup.current) {
        // This flag represents a genuinely untouched initialization placeholder,
        // never a guess based on an empty node list or an empty flow name.
        const connected = { ...createEmptyDraft(catalog), name: 'new_flow' };
        untouchedStartup.current = false;
        draftRef.current = connected; history.current = createDraftHistory(connected);
        setDraft(connected); setLoadedFlow(null); setDirty(false);
        setStatus('Project connected; choose a flow or create a new one');
      } else if (changingProject) {
        if (automatic) setStatus('Browser draft retained; refresh the project to use its task catalog');
        else requestAction({ kind: 'metadata', catalogText: JSON.stringify(next.metadata) });
      } else {
        try {
          const refreshed = parseDraft(serializeDraft({ ...current, catalog }));
          draftRef.current = refreshed; setDraft(refreshed);
        } catch {
          setStatus('Project metadata changed; current unsaved flow was retained. Reopen a flow after reconciling its task bindings.');
        }
      }
    } catch (cause) {
      if (externalSignal?.aborted || attempt !== connectionAttempt.current) return;
      const message = controller.signal.aborted ? 'The project connection timed out. Check the local editor and retry.' : cause instanceof Error ? cause.message : 'Could not connect to the local project';
      sessionRef.current = null; setSession(null);
      setConnectionPhase('failed'); setConnectionError(message);
      setSessionMessage('Disconnected: run this editor with weavem editor --project PATH');
      setStatus('Project connection unavailable; browser draft retained');
    } finally {
      window.clearTimeout(timeout);
      externalSignal?.removeEventListener('abort', abort);
    }
  }, [requestApi, requestAction]);

  useEffect(() => {
    const controller = new AbortController();
    // Deferring one tick avoids a duplicate bootstrap during StrictMode's
    // development effect replay, without coupling connection to draft edits.
    const timer = window.setTimeout(() => { void connectProject(true, controller.signal); }, 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [connectProject]);

  const saveFlow = useCallback(async (saveAs = false, nameOverride?: string, acquireLock = true): Promise<LoadedFlow> => {
    if (acquireLock) {
      if (submittingRef.current || executionActive) throw new Error('A save or run is already in progress.');
      submittingRef.current = true;
      setSubmitting(true);
    }
    try {
    if (!sessionMatchesDraft || !session) throw new Error('Connect this project before saving a flow.');
    if (!visualEditingAllowed) throw new Error(loadedFlow?.reason ?? 'This source flow cannot be rewritten visually.');
    const name = (nameOverride ?? draft.name).trim();
    if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(name)) throw new Error('Flow name must start with a letter and use only letters, numbers, and underscores.');
    if (parameterPending || (selectedNode && JSON.stringify(parseParameters(parameterText)) !== JSON.stringify(selectedNode.parameters))) {
      throw new Error('Apply the edited parameters before saving this flow');
    }
    const submittedSnapshot = serializeDraft(draft);
    const candidate = { ...draft, name };
    const graph = executionGraph(candidate, session.bindings);
    const expectedRevision = saveAs || !loadedFlow || loadedFlow.name !== name ? null : loadedFlow.revision;
    const saved = await requestApi<SavedFlowResponse>(`/api/flows/${encodeURIComponent(name)}`, {
      method: 'POST', body: JSON.stringify({ graph, layout: flowLayout(candidate), expectedRevision }),
    });
    const next: LoadedFlow = { name: saved.name, revision: saved.revision, editable: saved.editable ?? true, reason: saved.reason, source: saved.source };
    setLoadedFlow(next);
    // A save result only clears dirty state for the exact graph/layout that
    // was submitted. This also keeps a future non-UI caller safe.
    if (serializeDraft(draftRef.current) === submittedSnapshot) {
      setDraft((current) => ({ ...current, name }));
      draftRef.current = candidate;
      setDirty(false);
    }
    setFlowSummaries((current) => [...current.filter((flow) => flow.name !== next.name), { name: next.name, revision: saved.revision, editable: next.editable, reason: next.reason }].sort((left, right) => left.name.localeCompare(right.name)));
    setStatus(`Saved flow ${name}`);
    return next;
    } finally {
      if (acquireLock) { submittingRef.current = false; setSubmitting(false); }
    }
  }, [draft, executionActive, loadedFlow, parameterPending, parameterText, requestApi, selectedNode, session, sessionMatchesDraft, visualEditingAllowed]);

  const startRun = useCallback(async () => {
    if (submittingRef.current || executionActive) return;
    if (!sessionMatchesDraft || !session) { setRunError('Connect this project and load its catalog before running.'); return; }
    // Lock before the first save await so a double-click cannot submit a stale
    // graph or let the user mutate the flow between save and execution.
    submittingRef.current = true;
    setSubmitting(true);
    try {
      let target = loadedFlow;
      // The UI never executes a browser graph. Saving is the handoff to the
      // same ordinary Python flow used by CLI and Python callers.
      if (dirty || !target || target.name !== draft.name.trim()) target = await saveFlow(!target || target.name !== draft.name.trim(), undefined, false);
      const started = await requestApi<{ runId: string; status: RunState['status']; flowName?: string; revision?: string }>('/api/runs', {
        method: 'POST', body: JSON.stringify({ flowName: target.name, revision: target.revision, params: parseParameters(runParametersText) }),
      });
      revisionMismatchedRun.current = null;
      setRun({ runId: started.runId, status: started.status, nodes: {}, logs: '' });
      setRunError(null); setStatus('Run started');
    } catch (cause) { setRunError(cause instanceof Error ? cause.message : String(cause)); }
    finally { submittingRef.current = false; setSubmitting(false); }
  }, [dirty, draft.name, executionActive, loadedFlow, requestApi, runParametersText, saveFlow, session, sessionMatchesDraft]);

  const cancelRun = useCallback(async () => {
    if (!run || run.status !== 'running') return;
    try { await requestApi(`/api/runs/${encodeURIComponent(run.runId)}/cancel`, { method: 'POST', body: '{}' }); setStatus('Cancelling run…'); }
    catch (cause) { setRunError(cause instanceof Error ? cause.message : String(cause)); }
  }, [requestApi, run]);

  useEffect(() => {
    if (!activeRunToAttach || !session || pending) return;
    let cancelled = false;
    const attach = async () => {
      try {
        let state = await requestApi<RunState>(`/api/runs/${encodeURIComponent(activeRunToAttach)}`);
        if (cancelled) return;
        if (state.flowName) {
          // The active run must display the exact saved flow. Keep any browser
          // draft recoverable before replacing the visible canvas.
          saveStoredDraft(storage, draftRef.current);
          const attached = await loadFlow(state.flowName);
          if (state.revision && attached?.revision && state.revision !== attached.revision) {
            revisionMismatchedRun.current = state.runId;
            state = { ...state, nodes: {}, logs: `${state.logs}${state.logs ? '\n' : ''}The project flow has changed since this run started; node results are not shown on the current canvas.` };
          }
        }
        if (!cancelled) {
          setRun(state);
          setActiveRunToAttach(null);
          setStatus('Reattached to active run');
        }
      } catch (cause) {
        if (!cancelled) {
          setRunError(cause instanceof Error ? cause.message : String(cause));
          setActiveRunToAttach(null);
        }
      }
    };
    void attach();
    return () => { cancelled = true; };
  }, [activeRunToAttach, loadFlow, pending, requestApi, session, storage]);

  useEffect(() => {
    if (!run || run.status !== 'running') return undefined;
    let cancelled = false;
    let timer: number | undefined;
    const controller = new AbortController();
    const poll = async () => {
      try {
        let next = await requestApi<RunState>(`/api/runs/${encodeURIComponent(run.runId)}`, { signal: controller.signal });
        if (revisionMismatchedRun.current === run.runId) next = { ...next, nodes: {} };
        if (!cancelled) setRun(next);
        if (next.status !== 'running') return;
      } catch (cause) { if (!cancelled) setRunError(cause instanceof Error ? cause.message : String(cause)); }
      if (!cancelled) timer = window.setTimeout(() => { void poll(); }, 500);
    };
    void poll();
    return () => { cancelled = true; controller.abort(); window.clearTimeout(timer); };
  }, [requestApi, run?.runId, run?.status]);

  useEffect(() => {
    if (!run || run.status === 'running') return;
    setStatus(`Run ${run.status}`);
    setLogOpen(true);
  }, [run?.runId, run?.status]);

  useEffect(() => {
    if (autosavePaused || untouchedStartup.current) return undefined;
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
      if (executionActive || (!canvasEditingAllowed && !resumeAutosave)) {
        setError('The draft is locked while a run is active. Cancel or wait for it to finish.');
        return;
      }
      untouchedStartup.current = false;
      if (resumeAutosave) { history.current = createDraftHistory(next); setSampleRun(null); }
      else {
        const group = message === 'Nodes moving' ? 'drag' : message === 'Editing flow name' ? 'name' : message === 'Editing node details' ? 'details' : null;
        if (group && editGroup.current === group) history.current = { ...history.current, present: structuredClone(next) };
        else history.current = commitDraft({ ...history.current, present: structuredClone(draftRef.current) }, next);
        editGroup.current = group;
      }
      refreshHistory((value) => value + 1);
      draftRef.current = next;
      setDraft(next);
      if (next.catalog.kind === 'project') setDirty(true);
      if (resumeAutosave) {
        setAutosavePaused(false);
        setError(null);
      }
      if (message) setStatus(message);
      // A run describes the exact draft submitted to the local process. Never
      // leave that result attached to a subsequently edited draft.
      setRun(null);
    },
    [executionActive, canvasEditingAllowed],
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
    if (!canvasEditingAllowed) return;
    try {
      const next = addTask(draft, key, position ?? centerPosition());
      const added = next.nodes.at(-1);
      updateDraft(next, 'Task added to draft');
      setSelectedId(added?.id ?? null);
    } catch (cause) {
      setError(String(cause));
    }
  }, [canvasEditingAllowed, centerPosition, draft, updateDraft]);

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
    if (next !== draft) updateDraft(next, changes.some((change) => change.type === 'position') ? 'Nodes moving' : 'Draft updated');
    if (changes.some((change) => change.type === 'position' && change.dragging === false)) editGroup.current = null;
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
      if (!canvasEditingAllowed || !connection.source || !connection.target) return;
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
    if (!canvasEditingAllowed || !connection.source || !connection.target) return;
    try {
      const next = reconnectNodes(draft, oldEdge.id, connection.source, connection.target);
      reconnecting.current.set(oldEdge.id, { updated: true, escaped: false });
      updateDraft(next, oldEdge.target === connection.target ? 'Connection reconnected' : 'Connection reconnected; check mapping');
      selectEdge(oldEdge.id);
    } catch (cause) { setError(String(cause)); }
  }, [draft, canvasEditingAllowed, selectEdge, updateDraft]);

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
    if (!canvasEditingAllowed) return;
    const ids = selectedNodeIds.size ? selectedNodeIds : new Set(selectedId ? [selectedId] : []);
    if (!ids.size && !selectedEdgeIds.size) return;
    updateDraft({ ...draft, nodes: draft.nodes.filter((node) => !ids.has(node.id)),
      edges: draft.edges.filter((edge) => !ids.has(edge.source) && !ids.has(edge.target) && !selectedEdgeIds.has(edge.id)) }, 'Selection deleted');
    setSelectedEdgeIds(new Set()); setSelectedNodeIds(new Set()); setSelectedId(null);
  }, [canvasEditingAllowed, draft, selectedNodeIds, selectedEdgeIds, selectedId, updateDraft]);

  const restoreHistory = (direction: 'undo' | 'redo') => {
    if (!canvasEditingAllowed) return;
    history.current = direction === 'undo' ? undoDraft(history.current) : redoDraft(history.current);
    const restored = { ...history.current.present, viewport: draftRef.current.viewport };
    draftRef.current = restored; setDraft(restored); setDirty(true); setRun(null);
    setSelectedId(null); setSelectedNodeIds(new Set()); setSelectedEdgeIds(new Set());
    editGroup.current = null; refreshHistory((value) => value + 1);
  };
  const copyNodes = () => {
    clipboard.current = copySelection(draft, selectedNodeIds.size ? selectedNodeIds : new Set(selectedId ? [selectedId] : []));
    refreshHistory((value) => value + 1);
  };
  const pasteNodes = () => {
    if (!canvasEditingAllowed || !clipboard.current) return;
    const pasted = pasteSelection(draft, clipboard.current);
    updateDraft(pasted.draft, 'Selection pasted'); setSelectedNodeIds(pasted.nodeIds); setSelectedId([...pasted.nodeIds][0] ?? null);
  };
  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (pending || saveAsOpen) return;
    const target = event.target as HTMLElement;
    if (target.closest('input, textarea, select, [contenteditable=true]')) return;
    if ((event.ctrlKey || event.metaKey) && canvasEditingAllowed) {
      const key = event.key.toLowerCase();
      if (key === 'z') { event.preventDefault(); restoreHistory(event.shiftKey ? 'redo' : 'undo'); return; }
      if (key === 'y') { event.preventDefault(); restoreHistory('redo'); return; }
      if (key === 'c') { event.preventDefault(); copyNodes(); return; }
      if (key === 'v') { event.preventDefault(); pasteNodes(); return; }
    }
    if (event.key === 'Escape') reconnecting.current.forEach((attempt) => { attempt.escaped = true; });
    if ((event.key === 'Delete' || event.key === 'Backspace') && target.tagName !== 'BUTTON') { event.preventDefault(); deleteSelected(); }
  };

  const setName = (name: string) => updateDraft({ ...draft, name }, 'Editing flow name');
  const updateSelected = (changes: Partial<Pick<DraftNode, 'label' | 'notes' | 'parameters'>>) => {
    if (!selectedNode) return;
    updateDraft({
      ...draft,
      nodes: draft.nodes.map((node) => (
        node.id === selectedNode.id ? { ...node, ...changes } : node
      )),
    }, changes.parameters ? 'Parameters applied' : 'Editing node details');
  };

  useEffect(() => {
    if (!pending && !saveAsOpen) {
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
        if (saveAsOpen && submittingRef.current) return;
        setPending(null);
        setSaveAsOpen(false);
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
  }, [pending, saveAsOpen]);

  const executePending = useCallback(async (action: PendingAction) => {
    try {
      if (action.kind === 'attach') {
        setSession(action.session);
        setFlowSummaries(action.session.flows ?? []);
        setSessionMessage(`Connected to ${action.session.project}`);
        setRunError(null);
        setActiveRunToAttach(action.runId);
        setPending(null);
        return;
      }
      if (action.kind === 'flow') {
        await loadFlow(action.name);
        setPending(null);
        return;
      }
      let next: EditorDraft;
      if (action.kind === 'new') {
        next = { ...createEmptyDraft(draft.catalog), name: draft.catalog.kind === 'project' ? 'new_flow' : 'Untitled draft' };
        updateDraft(next, 'New empty flow', true);
        setLoadedFlow(null); setDirty(false);
      } else if (action.kind === 'metadata') {
        const catalog = importMetadata(action.catalogText);
        next = { ...createEmptyDraft(catalog), name: catalog.kind === 'project' ? 'new_flow' : catalog.name };
        updateDraft(next, 'Project catalog connected; new flow started', true);
        setLoadedFlow(null); setDirty(false);
      } else {
        next = parseDraft(action.draftText);
        updateDraft(next, 'Draft opened from file', true);
        setLoadedFlow(null); setDirty(next.catalog.kind === 'project');
      }
      setSelectedId(null);
      setSelectedNodeIds(new Set());
      setSelectedEdgeIds(new Set());
      window.requestAnimationFrame(() => flow?.setViewport(next.viewport));
      setPending(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setPending(null);
    }
  }, [draft.catalog, flow, loadFlow, updateDraft]);


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
      <section className="desktop-notice" aria-label="Desktop requirement" inert={pending || saveAsOpen ? true : undefined}>
        <div>
          <strong>Weavem node editor is a desktop workbench.</strong>
          <span>Open this draft on a screen at least 1100px wide to edit it.</span>
        </div>
        <Button variant="primary" onClick={exportDraft}>
          {icon('download')} Export draft
        </Button>
      </section>
      <div ref={workbench} className="workbench" style={{ '--library-width': `${layout.libraryWidth}px`, '--inspector-width': `${layout.inspectorWidth}px` } as React.CSSProperties} inert={pending || saveAsOpen ? true : undefined}>
        <header className="topbar">
          <div className="topbar-main">
            <div className="brand">
              <span className="brand-mark">W</span>
              <span>weavem</span>
            </div>
            <details className="project-environment">
              <summary>Project environment</summary>
              <div className="project-environment-content">
                <p>{session?.project ?? 'No project connected'}</p>
                <code>{session?.environment?.pythonExecutable ?? 'Interpreter unavailable'}</code>
                <p>{session?.environment ? `Python ${session.environment.pythonVersion} · Weavem ${session.environment.weavemVersion}` : 'Runtime version information unavailable'}</p>
              </div>
            </details>
          </div>
          <EditorToolbar busy={executionActive} isProjectFlow={sessionMatchesDraft} canEdit={canvasEditingAllowed}
            flowName={draft.name} onFlowNameChange={setName} onFlowNameBlur={() => { editGroup.current = null; }} onNew={() => requestAction({ kind: 'new' })}
            onImportMetadata={() => metadataInput.current?.click()} onOpenFlow={(name) => requestAction({ kind: 'flow', name })}
            flows={flowSummaries} onSave={() => void saveFlow(false).catch((cause: unknown) => setError(String(cause)))}
            onSaveAs={() => { previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; setSaveAsError(null); setSaveAsName(`${draft.name.trim() || 'new_flow'}_copy`); setSaveAsOpen(true); }}
            onOpenDraft={() => draftInput.current?.click()} onExportDraft={exportDraft} onConnectProject={() => void connectProject()}
            connected={Boolean(session)} canUndo={canvasEditingAllowed && canUndo(history.current)} canRedo={canvasEditingAllowed && canRedo(history.current)}
            canCopy={Boolean(selectedId || selectedNodeIds.size)} canPaste={canvasEditingAllowed && Boolean(clipboard.current)}
            onUndo={() => restoreHistory('undo')} onRedo={() => restoreHistory('redo')} onCopy={copyNodes} onPaste={pasteNodes}
            runParameters={runParametersText} onRunParametersChange={setRunParametersText} canRun={sessionMatchesDraft} runControl={runControl()}
            icons={{ plus: icon('plus'), file: icon('file'), folder: icon('folder'), download: icon('download') }} />
          <nav className="editor-view-tabs" aria-label="Editor view">
            <Button aria-pressed={!inspectRun} onClick={() => setInspectRun(false)}>Edit flow</Button>
            <Button disabled={!sessionMatchesDraft || !loadedFlow} aria-pressed={inspectRun} onClick={() => { void requestApi<RunInspectionRecord | { inspection: null }>(`/api/flows/${encodeURIComponent(loadedFlow!.name)}/last-run`).then((value) => { setInspection('inspection' in value ? null : value); setInspectRun(true); }).catch((cause: unknown) => setError(String(cause))); }}>Last run</Button>
            {run && <Button aria-pressed={logOpen} onClick={() => setLogOpen((open) => !open)}>{logOpen ? 'Hide run log' : 'Show run log'}</Button>}
          </nav>
          <div className="save-state" role="status">
            <span className={autosavePaused ? 'status-dot warning' : 'status-dot'} />
            {autosavePaused ? 'Autosave paused' : status}
          </div>
          <input
            ref={metadataInput}
            className="visually-hidden"
            aria-label="Import metadata JSON"
            type="file"
            tabIndex={-1}
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
            tabIndex={-1}
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
              <span className="visually-hidden">Task library</span>
              <h1>{draft.catalog.name}</h1>
            </div>
            <span className={`catalog-badge ${draft.catalog.kind}`}>
              {sessionMatchesDraft ? 'Project metadata' : 'Browser draft'}
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
                draggable={canvasEditingAllowed}
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
                <button className="add-task" disabled={!canvasEditingAllowed} aria-label={`Add task ${task.taskId}`} onClick={() => addCatalogTask(task.key)}>
                  {icon('plus')} Add task
                </button>
              </article>
            ))}
            {visibleTasks.length === 0 && <p className="empty-list">{draft.catalog.tasks.length ? 'No tasks match this search.' : sessionMatchesDraft ? 'No tasks are registered in this project.' : 'Connect a project to discover its tasks.'}</p>}
          </div>
        </aside>
        <ResizeHandle side="library" width={layout.libraryWidth} onResize={(width) => updatePanelWidth('library', width)} />

        {inspectRun && <div className="last-run-overlay">{inspection ? <RunInspection inspection={inspection} onClose={() => setInspectRun(false)} /> : <section className="panel"><h2>Last run</h2><p>No recorded run for this flow.</p><Button onClick={() => setInspectRun(false)}>Edit flow</Button></section>}</div>}
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
          {connectionPhase === 'loading' && <div className="connection-notice" role="status">Connecting to the local project…</div>}
          {connectionPhase === 'failed' && <div className="connection-notice"><p role="status">{connectionError}</p><p>Start the editor with <code>weavem editor --project PATH</code>, then retry.</p><Button onClick={() => void connectProject(true)}>Retry connection</Button></div>}
          {connectionPhase === 'connected' && session && !sessionMatchesDraft && <div className="connection-notice"><p>Your browser draft is preserved. Refresh the project to use its task catalog.</p><Button onClick={() => void connectProject()}>Use project catalog</Button></div>}
          <div className="canvas-header">
            <div>
              <span className="eyebrow">Composition draft</span>
              <span className="canvas-summary">{draft.nodes.length} nodes · {draft.edges.length} connections</span>
            </div>
            {canvasFullscreen && <div className="canvas-run-action">
              {runControl()}
              {run && <Button aria-pressed={logOpen} onClick={() => setLogOpen((open) => !open)}>{logOpen ? 'Hide run log' : 'Show run log'}</Button>}
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
            edgesReconnectable={canvasEditingAllowed}
            onReconnectStart={onReconnectStart}
            onReconnect={reconnectEdge}
            onReconnectEnd={onReconnectEnd}
            onPointerCancelCapture={() => reconnecting.current.forEach((attempt) => { attempt.escaped = true; })}
            nodesDraggable={canvasEditingAllowed}
            nodesConnectable={canvasEditingAllowed}
            elementsSelectable={!executionActive}
            onSelectionChange={onSelectionChange}
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
            onMoveEnd={(event, viewport) => { if (!executionActive && visualEditingAllowed) { if (event) untouchedStartup.current = false; setDraft((current) => ({ ...current, viewport })); if (draft.catalog.kind === 'project') setDirty(true); } }}
            defaultViewport={draft.viewport ?? defaultViewport}
            deleteKeyCode={null}
            multiSelectionKeyCode={['Meta', 'Control']}
            aria-label="Weavem draft graph"
          >
            <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="var(--color-line)" />
            <Controls showInteractive={false} />
            <MiniMap
              nodeColor={(node) => (node.data as NodeData).task?.provenance === 'released' ? 'var(--color-released)' : 'var(--color-accent)'}
              maskColor="var(--color-canvas-mask)"
            />
          </ReactFlow>
          {loadedFlow && !loadedFlow.editable && (
            <div className="source-only-notice" role="note">Source flow: {loadedFlow.reason ?? 'The canvas cannot safely rewrite this Python source.'} You can still run it with JSON parameters.</div>
          )}
          {draft.nodes.length === 0 && (!loadedFlow || loadedFlow.editable) && (
            <div className="canvas-empty">
              <span className="empty-mark">+</span>
              <strong>{sessionMatchesDraft ? 'Choose a flow or create a new one.' : 'Your browser draft'}</strong>
              <p>{sessionMatchesDraft ? 'Open a saved flow above, or add tasks from the library.' : 'Connect a project to discover tasks. You can still open or export a browser draft.'}</p>
            </div>
          )}
          <div className="canvas-footer">{executionActive ? (run?.phase === 'preparing' ? (run.message ?? 'Preparing flow…') : `Run ${run?.runId ?? 'submission'} is active; editing is locked`) : sessionMatchesDraft ? 'Ready to run · connections require target argument mapping' : 'Draft wiring · connect a local project to run'}</div>
          {run && logOpen && <section className="run-log panel" aria-label="Run log"><div className="panel-heading"><div><h2>{run.status === 'running' && run.phase === 'preparing' ? (run.message ?? 'Preparing flow…') : run.status}</h2></div><button className="icon-button" aria-label="Hide run log" onClick={() => setLogOpen(false)}>{icon('x')}</button></div><code>{run.runId}{run.flowName ? ` · ${run.flowName}${run.revision ? ` @ ${run.revision}` : ''}` : ''}</code><pre>{run.logs || 'Waiting for task output…'}</pre><ResultViewer value={run.resultValue} fallback={run.result} />{run.error && <p role="alert">{run.error}</p>}{run.errorDetails && <pre aria-label="Failure details">{JSON.stringify(run.errorDetails, null, 2)}</pre>}</section>}
        </section>
        <ResizeHandle side="inspector" width={layout.inspectorWidth} onResize={(width) => updatePanelWidth('inspector', width)} />

        <aside className="inspector panel" aria-label="Node inspector">
          <div className="panel-heading inspector-panel-heading">
            <div>
              <span className="visually-hidden">Inspector</span>
              <h2>{selectedNode && selectedTask ? selectedNode.label : selectedEdge ? 'Connection' : 'Nothing selected'}</h2>
              {selectedNode && selectedTask && <div className="inspector-header-identity">
                <code>{selectedTask.taskId}</code>
                <div className="task-tags inspector-identity-tags">
                  <span>{selectedTask.version}</span>
                  <span>{selectedTask.backend}</span>
                  <span className={`provenance ${selectedTask.provenance}`}>{selectedTask.provenance}</span>
                  {selectedRunResult && <span className={`node-run-status ${selectedRunResult.status}`}>{selectedRunResult.status}</span>}
                </div>
              </div>}
              {selectedEdge && <p className="inspector-connection-route">{selectedEdgeSource?.label ?? selectedEdge.source} → {selectedEdgeTarget?.label ?? selectedEdge.target}</p>}
            </div>
          </div>
          {selectedNode && selectedTask ? <div className="inspector-content">
            <InspectorSection name="parameters" title="Parameters" open={inspectorSections.parameters} onToggle={toggleInspectorSection}>
              <ParameterEditor
                key={selectedNode.id}
                value={parameterText}
                onChange={setParameterText}
                onApply={applyParameters}
                disabled={!canvasEditingAllowed}
                hints={session?.parameterHints?.[selectedNode.taskKey]}
                wired={wiredParameters}
                onPendingChange={setParameterPending}
              />
            </InspectorSection>
            <InspectorSection name="connections" title="Connections" open={inspectorSections.connections} onToggle={toggleInspectorSection}>
              {(['incoming', 'outgoing'] as const).map((direction) => {
                const connected = draft.edges.filter((edge) => direction === 'incoming' ? edge.target === selectedNode.id : edge.source === selectedNode.id);
                const title = direction === 'incoming' ? 'Incoming connections' : 'Outgoing connections';
                return <section className="connection-group" key={direction} aria-label={title}>
                  <div className="connection-heading">
                    <h3>{title}</h3>
                    {direction === 'outgoing' && <button type="button" className="connection-add-toggle" aria-expanded={connectionAdderOpen} aria-controls="add-outgoing-connection" disabled={!canvasEditingAllowed} onClick={() => setConnectionAdderOpen((open) => !open)}>{icon('plus')} Add connection</button>}
                  </div>
                  {connected.length ? connected.map((edge) => {
                    const otherId = direction === 'incoming' ? edge.source : edge.target;
                    const otherLabel = draft.nodes.find((node) => node.id === otherId)?.label ?? otherId;
                    return <div className="connection-row" key={`${edge.id}:${edge.argument ?? ''}`}>
                      <button type="button" disabled={!canvasEditingAllowed} onClick={() => selectEdge(edge.id)} aria-label={`Select connection ${direction === 'incoming' ? 'from' : 'to'} ${otherLabel}`}><span>{direction === 'incoming' ? '←' : '→'} {otherLabel}</span></button>
                      <input aria-label={`Connection target argument to ${otherLabel}`} list={`connection-arguments-${edge.id}`} disabled={!canvasEditingAllowed} defaultValue={edge.argument ?? ''} placeholder="Mapping required" onBlur={(event) => {
                        const value = event.currentTarget.value.trim();
                        if (value === (edge.argument ?? '')) return;
                        try {
                          updateDraft(value ? setEdgeArgument(draft, edge.id, value) : clearEdgeArgument(draft, edge.id), value ? 'Connection argument mapped' : 'Connection mapping cleared');
                        } catch (cause) { setError(String(cause)); }
                      }} />
                      <FieldMapping key={`${edge.id}:${JSON.stringify(edge.sourcePath)}`} path={edge.sourcePath} disabled={!canvasEditingAllowed}
                        fields={session?.parameterHints?.[draft.nodes.find((node) => node.id === edge.source)?.taskKey ?? '']?.output?.fields}
                        observed={sampleRun?.nodes[edge.source]?.value} runId={sampleRun?.runId}
                        onApply={(path) => updateDraft(setEdgeSourcePath(draft, edge.id, path), 'Upstream field mapped')} />
                      <datalist id={`connection-arguments-${edge.id}`}>
                        {eligibleTargetArguments(draft, edge.target, edge.id).map((argument) => <option key={argument} value={argument} />)}
                      </datalist>
                      <button type="button" disabled={!canvasEditingAllowed} className="connection-delete" aria-label={`Delete connection to ${otherLabel}`} onClick={() => deleteEdge(edge.id)}>Delete</button>
                    </div>;
                  }) : <p className="connection-empty">No {direction} draft connections.</p>}
                  {direction === 'outgoing' && <div id="add-outgoing-connection" className="connection-add-form" hidden={!connectionAdderOpen}>
                    <Field label="Connect to">
                      <select aria-label="Add connection target" disabled={!canvasEditingAllowed} value={targetAvailable ? connectTarget : ''} onChange={(event) => setConnectTarget(event.target.value)}>
                        <option value="" disabled>Select a draft node</option>
                        {connectionTargets.map(({ node, connected, available }) => <option key={node.id} value={node.id} disabled={!available}>{node.label}{connected ? available ? ' (connected · another input available)' : ' (connected)' : ''}</option>)}
                      </select>
                    </Field>
                    <Button variant="secondary" className="wide" onClick={() => { if (targetAvailable) { addConnection({ source: selectedNode.id, target: connectTarget }); setConnectTarget(''); setConnectionAdderOpen(false); } }} disabled={!targetAvailable || !canvasEditingAllowed}>Connect</Button>
                  </div>}
                </section>;
              })}
            </InspectorSection>
            {selectedRunResult && <InspectorSection name="result" title="Result" open={inspectorSections.result} onToggle={toggleInspectorSection}>
              <section className="run-result" aria-label="Run result"><p className={`run-result-status ${selectedRunResult.status}`}>{selectedRunResult.status}</p><ResultViewer value={selectedRunResult.value} fallback={selectedRunResult.preview} />{selectedRunResult.error && <p role="alert">{selectedRunResult.error}</p>}{selectedRunResult.errorDetails && <dl className="metadata-list"><div><dt>Code</dt><dd>{selectedRunResult.errorDetails.code ?? 'Unclassified'}</dd></div><div><dt>Input</dt><dd>{selectedRunResult.errorDetails.input ?? 'Unknown'}</dd></div><div><dt>Remediation</dt><dd>{selectedRunResult.errorDetails.remediation ?? 'None supplied'}</dd></div><div><dt>Retryable</dt><dd>{selectedRunResult.errorDetails.retryable === undefined || selectedRunResult.errorDetails.retryable === null ? 'Unknown' : String(selectedRunResult.errorDetails.retryable)}</dd></div></dl>}</section>
            </InspectorSection>}
            <InspectorSection name="details" title="Details" open={inspectorSections.details} onToggle={toggleInspectorSection}>
              <Field label="Node label">
                <input disabled={!canvasEditingAllowed} value={selectedNode.label} onBlur={() => { editGroup.current = null; }} onChange={(event) => updateSelected({ label: event.target.value })} />
              </Field>
              <Field label="Notes">
                <textarea disabled={!canvasEditingAllowed} value={selectedNode.notes} onBlur={() => { editGroup.current = null; }} onChange={(event) => updateSelected({ notes: event.target.value })} placeholder="Private drafting note" />
              </Field>
              <dl className="metadata-list">
                <div><dt>Inputs</dt><dd>{selectedTask.inputs.length ? selectedTask.inputs.join(', ') : 'None declared'}</dd></div>
                <div><dt>Output</dt><dd>{selectedTask.output || 'None declared'}</dd></div>
                <div><dt>Source</dt><dd className="mono-break">{selectedTask.source}</dd></div>
                {selectedTask.manifestSha256 && <div><dt>Manifest hash</dt><dd className="mono-break">{selectedTask.manifestSha256}</dd></div>}
              </dl>
            </InspectorSection>
            <button className="delete-button" disabled={!canvasEditingAllowed} onClick={deleteSelected}>Delete node</button>
          </div> : selectedEdge ? <div className="inspector-content connection-inspector-content">
            <section className="connection-editor" aria-label="Connection mapping">
              <p className="field-help">Pass the whole upstream result or select a nested field for a target argument.</p>
              <FieldMapping key={`${selectedEdge.id}:${JSON.stringify(selectedEdge.sourcePath)}`} path={selectedEdge.sourcePath} disabled={!canvasEditingAllowed}
                fields={session?.parameterHints?.[selectedEdgeSource?.taskKey ?? '']?.output?.fields}
                observed={sampleRun?.nodes[selectedEdge.source]?.value} runId={sampleRun?.runId}
                onApply={(path) => updateDraft(setEdgeSourcePath(draft, selectedEdge.id, path), 'Upstream field mapped')} />
              <Field label="Target argument"><input aria-label="Connection target argument" disabled={!canvasEditingAllowed} value={edgeArgument} placeholder="for example: text" onChange={(event) => setEdgeArgumentText(event.target.value)} /></Field>
              <Button variant="secondary" className="wide" disabled={!canvasEditingAllowed || !edgeArgument.trim()} onClick={() => { try { updateDraft(setEdgeArgument(draft, selectedEdge.id, edgeArgument), 'Connection argument mapped'); } catch (cause) { setError(String(cause)); } }}>Apply mapping</Button>
            </section>
            <button className="delete-button" disabled={!canvasEditingAllowed} onClick={() => deleteEdge(selectedEdge.id)}>Delete connection</button>
          </div> : <div className="inspector-empty"><span className="empty-mark">↖</span><p>Select a task node to view descriptive metadata and edit this draft instance.</p><small>Connections need explicit argument mappings before a run.</small></div>}
        </aside>
        <footer className="bottom-status">
          <span>{error || runError ? 'Attention needed' : sessionMessage}</span>
          {error || runError ? <span role="alert">{error ?? runError}</span> : <span>{run ? `Run ${run.status}. ${run.error ?? ''}` : 'Autosaved locally in this browser. Export a file to move the draft.'}</span>}
        </footer>
      </div>

      {saveAsOpen && <div className="modal-backdrop" role="presentation"><section ref={dialog} className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="save-as-title"><h2 id="save-as-title">Create an ordinary project flow</h2><Field label="New flow name"><input aria-label="New flow name" disabled={submitting} value={saveAsName} onChange={(event) => setSaveAsName(event.target.value)} /></Field><p>Use a Python identifier. This writes standard flow files into the first configured flow directory.</p>{saveAsError && <p role="alert">{saveAsError}</p>}<div className="dialog-actions"><Button disabled={submitting} onClick={() => setSaveAsOpen(false)}>Cancel</Button><Button variant="primary" disabled={submitting} onClick={() => void saveFlow(true, saveAsName).then(() => setSaveAsOpen(false)).catch((cause: unknown) => setSaveAsError(cause instanceof Error ? cause.message : String(cause)))}>Save as</Button></div></section></div>}
      {pending && <div className="modal-backdrop" role="presentation"><section ref={dialog} className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="replace-title"><h2 id="replace-title">Your current graph will be replaced.</h2><p>Export it first if you need a portable copy. Invalid files never change the current draft.</p><div className="dialog-actions"><Button onClick={() => setPending(null)}>Cancel</Button><Button variant="primary" onClick={() => void executePending(pending)}>Replace draft</Button></div></section></div>}
    </main>
  );
}
