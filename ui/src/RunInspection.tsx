import type { ProjectFlow, RunState } from './types';

type Snapshot = {
  flowName: string;
  revision: string;
  startedAt?: string | null;
  graph?: ProjectFlow['graph'];
  source?: string | null;
  params?: Record<string, unknown>;
  catalog?: { metadata?: { tasks?: Array<{ taskId?: string }> } };
};

type Inspection = { runId: string; snapshot: Snapshot; state?: RunState | null };

type Props = { inspection: Inspection | null; onClose: () => void };

/** Read-only evidence for a saved flow run; never edits the current draft. */
export function RunInspection({ inspection, onClose }: Props) {
  if (!inspection) return null;
  const { snapshot, state } = inspection;
  const graph = snapshot.graph;
  return <section className="run-inspection panel" aria-label="Last run">
    <header className="panel-heading"><div><p className="eyebrow">Execution evidence</p><h2>Last run</h2></div><button className="icon-button" aria-label="Close last run" onClick={onClose}>×</button></header>
    <dl>
      <dt>Run</dt><dd><code>{inspection.runId}</code></dd>
      <dt>Flow revision</dt><dd><code>{snapshot.revision}</code></dd>
      {snapshot.startedAt && <><dt>Started</dt><dd>{snapshot.startedAt}</dd></>}
      <dt>Status</dt><dd>{state?.status ?? 'recorded before completion'}</dd>
    </dl>
    <details open><summary>Inputs</summary><pre>{JSON.stringify(snapshot.params ?? {}, null, 2)}</pre></details>
    {graph ? <details open><summary>Executed graph ({graph.nodes.length} tasks)</summary><ol>{graph.nodes.map((node) => <li key={node.id}><strong>{node.id}</strong> · {node.taskKey}<br /><code>{JSON.stringify(node.parameters)}</code>{state?.nodes?.[node.id]?.preview && <pre>{state.nodes[node.id].preview}</pre>}</li>)}</ol></details>
      : <p className="source-only-notice">This handwritten flow was runnable but did not have a visual graph. Its source below is execution evidence only.</p>}
    {state?.error && <details open><summary>Error</summary><pre>{state.error}</pre></details>}
    {state?.result && <details open><summary>Result</summary><pre>{state.result}</pre></details>}
    {snapshot.source && <details><summary>Saved source</summary><pre>{snapshot.source}</pre></details>}
  </section>;
}
