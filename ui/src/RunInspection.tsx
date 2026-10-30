import type { ProjectFlow, RunState } from './types';
import { ResultViewer } from './ResultViewer';

type Snapshot = {
  flowName: string;
  revision: string;
  startedAt?: string | null;
  graph?: ProjectFlow['graph'];
  source?: string | null;
  params?: Record<string, unknown>;
  catalog?: { metadata?: { tasks?: Array<{ taskId?: string }> } };
};

export type RunInspectionRecord = { runId: string; tracking?: 'active' | 'untracked'; snapshot: Snapshot; state?: RunState | null };

type Props = { inspection: RunInspectionRecord | null; onClose: () => void };

/** Read-only evidence for a saved flow run; never edits the current draft. */
export function RunInspection({ inspection, onClose }: Props) {
  if (!inspection) return <section className="run-inspection panel" aria-label="Last run"><header className="panel-heading"><h2>Last run</h2><button className="icon-button" aria-label="Close last run" onClick={onClose}>×</button></header><p>No recorded run for this flow yet. Return to Edit flow and run the saved flow to capture results.</p></section>;
  const { snapshot, state } = inspection;
  const graph = snapshot.graph;
  return <section className="run-inspection panel" aria-label="Last run">
    <header className="panel-heading"><div><p className="eyebrow">Execution evidence</p><h2>Last run</h2></div><button className="icon-button" aria-label="Close last run" onClick={onClose}>×</button></header>
    <dl>
      <dt>Run</dt><dd><code>{inspection.runId}</code></dd>
      <dt>Flow revision</dt><dd><code>{snapshot.revision}</code></dd>
      {snapshot.startedAt && <><dt>Started</dt><dd>{snapshot.startedAt}</dd></>}
      {state && 'finishedAt' in state && <><dt>Finished</dt><dd>{String(state.finishedAt)}</dd></>}
      <dt>Status</dt><dd>{state?.status === 'running' && inspection.tracking === 'untracked' ? 'Last observed running; original editor session is no longer tracking this execution' : state?.status ?? 'recorded before completion'}</dd>
    </dl>
    <details open><summary>Inputs</summary><pre>{JSON.stringify(snapshot.params ?? {}, null, 2)}</pre></details>
    {graph ? <details open><summary>Executed graph ({graph.nodes.length} tasks)</summary><ol>{graph.nodes.map((node) => <li key={node.id}><strong>{node.id}</strong> · {node.taskKey}<br /><code>{JSON.stringify(node.parameters)}</code><span>{state?.nodes?.[node.id]?.status ?? 'Unknown'}</span><ResultViewer value={state?.nodes?.[node.id]?.value} fallback={state?.nodes?.[node.id]?.preview} />{state?.nodes?.[node.id]?.error && <p>{state.nodes[node.id].error}</p>}</li>)}</ol></details>
      : <p className="source-only-notice">This handwritten flow was runnable but did not have a visual graph. Its source below is execution evidence only.</p>}
    {graph && <details open><summary>Executed connections</summary><pre>{JSON.stringify(graph.edges, null, 2)}</pre></details>}
    {state?.errorDetails && <pre>{JSON.stringify(state.errorDetails, null, 2)}</pre>}
    {state?.error && <details open><summary>Error</summary><pre>{state.error}</pre></details>}
    <details open><summary>Result</summary><ResultViewer value={state?.resultValue} fallback={state?.result} /></details>
    {snapshot.source && <details><summary>Saved source</summary><pre>{snapshot.source}</pre></details>}
  </section>;
}
