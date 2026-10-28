import type { Catalog, DraftEdge, DraftNode } from './types';

/** Synthetic, non-executable starter content for the visual prototype. */
export const demoCatalog: Catalog = {
  name: 'Synthetic document pipeline',
  kind: 'demo',
  tasks: [
    {
      key: 'local:demo/read_documents', taskId: 'documents.read', version: '1.0.0', backend: 'python', provenance: 'local',
      description: 'Reads a selected document list into this draft pipeline.', inputs: ['paths'], output: 'documents', source: 'demo/read_documents',
    },
    {
      key: 'released:demo/normalize_text:9d26e39a0b452bf4379d907514f1da483471ad27004f5c9dd6c2799e742503a1', taskId: 'text.normalize', version: '1.2.0', backend: 'cython', provenance: 'released',
      description: 'A released native task shown only as catalog metadata.', inputs: ['documents'], output: 'normalized_documents', source: 'demo/normalize_text',
      manifestSha256: '9d26e39a0b452bf4379d907514f1da483471ad27004f5c9dd6c2799e742503a1',
    },
    {
      key: 'local:demo/count_words', taskId: 'text.count_words', version: '1.0.0', backend: 'python', provenance: 'local',
      description: 'Counts words for review; this graph does not execute it.', inputs: ['normalized_documents'], output: 'word_counts', source: 'demo/count_words',
    },
  ],
};

export const demoNodes: DraftNode[] = [
  { id: 'demo-read', taskKey: 'local:demo/read_documents', position: { x: 40, y: 170 }, label: 'Read documents', notes: 'Synthetic sample input.', parameters: { paths: ['brief.md', 'notes.md'] } },
  { id: 'demo-normalize', taskKey: 'released:demo/normalize_text:9d26e39a0b452bf4379d907514f1da483471ad27004f5c9dd6c2799e742503a1', position: { x: 365, y: 170 }, label: 'Normalize text', notes: 'Released Cython example.', parameters: { lowercase: true } },
  { id: 'demo-count', taskKey: 'local:demo/count_words', position: { x: 700, y: 170 }, label: 'Count words', notes: '', parameters: { include_headings: false } },
];

export const demoEdges: DraftEdge[] = [
  { id: 'demo-edge-read-normalize', source: 'demo-read', target: 'demo-normalize' },
  { id: 'demo-edge-normalize-count', source: 'demo-normalize', target: 'demo-count' },
];
