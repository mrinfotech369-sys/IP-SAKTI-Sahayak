'use client';

import { Background, Controls, Edge, MarkerType, MiniMap, Node, ReactFlow } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useParams } from 'next/navigation';
import { useMemo, useState } from 'react';
import { Badge, Card, ErrorState, Spinner } from '@/components/ui';
import { useInnovationData } from '@/lib/hooks';

const COLUMNS: Record<string, { x: number; color: string }> = {
  'Evidence Gap': { x: 0, color: '#A33B2F' },
  Claim: { x: 260, color: '#9A533B' },
  Feature: { x: 260, color: '#2B5C8A' },
  Ingredient: { x: 260, color: '#194C3D' },
  Innovation: { x: 560, color: '#123C30' },
  Patent: { x: 860, color: '#8A5A12' },
  'Scientific Study': { x: 860, color: '#2F6B4F' },
  'Traditional Knowledge Context': { x: 860, color: '#7A5B12' },
  Regulation: { x: 1160, color: '#1A2520' },
  Authority: { x: 1160, color: '#4F5A53' },
  Jurisdiction: { x: 1440, color: '#2B5C8A' },
};

export default function GraphTab() {
  const { id } = useParams<{ id: string }>();
  const q = useInnovationData(id, 'graph');
  const [sel, setSel] = useState<{ kind: 'node' | 'edge'; data: any } | null>(null);
  const [hidden, setHidden] = useState<string[]>([]);

  const { nodes, edges } = useMemo(() => {
    if (!q.data) return { nodes: [] as Node[], edges: [] as Edge[] };
    const counters: Record<number, number> = {};
    const visible = q.data.nodes.filter((n: any) => !hidden.includes(n.type));
    const ids = new Set(visible.map((n: any) => n.id));
    const nodes: Node[] = visible.map((n: any) => {
      const col = COLUMNS[n.type] || { x: 1440, color: '#666' };
      const y = (counters[col.x] = (counters[col.x] ?? -1) + 1) * 78;
      return {
        id: n.id, position: { x: col.x, y: n.type === 'Innovation' ? 240 : y }, data: { label: n.label, raw: n },
        style: { background: n.type === 'Innovation' ? col.color : '#FFFDF8', color: n.type === 'Innovation' ? '#fff' : '#1A2520', border: `2px solid ${col.color}`, borderRadius: 6, fontSize: 11, width: 210, padding: 6 },
      };
    });
    const edges: Edge[] = q.data.edges.filter((e: any) => ids.has(e.source) && ids.has(e.target)).map((e: any) => ({
      id: e.id, source: e.source, target: e.target, label: e.type, data: e,
      labelStyle: { fontSize: 9, fill: '#4F5A53' }, style: { stroke: e.type === 'REQUIRES_REVIEW' || e.type === 'HAS_GAP' ? '#A33B2F' : '#9a9a8c' },
      markerEnd: { type: MarkerType.ArrowClosed },
    }));
    return { nodes, edges };
  }, [q.data, hidden]);

  if (q.isLoading) return <Spinner label="Building evidence graph…" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const types = Array.from(new Set(q.data.nodes.map((n: any) => n.type))) as string[];
  const connected = sel?.kind === 'node' ? q.data.edges.filter((e: any) => e.source === sel.data.id || e.target === sel.data.id) : [];
  const label = (nid: string) => q.data.nodes.find((n: any) => n.id === nid)?.label || nid;

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
      <div>
        <div className="mb-2 flex flex-wrap gap-2 text-xs" role="group" aria-label="Node types">
          {types.map((t) => (
            <label key={t} className="flex items-center gap-1 rounded border border-surface-border bg-surface px-2 py-1">
              <input type="checkbox" checked={!hidden.includes(t)} onChange={(e) => setHidden(e.target.checked ? hidden.filter((h) => h !== t) : [...hidden, t])} />
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: COLUMNS[t]?.color }} /> {t}
            </label>
          ))}
        </div>
        <div className="h-[640px] rounded-lg border border-surface-border bg-surface-elevated">
          <ReactFlow nodes={nodes} edges={edges} fitView minZoom={0.2}
            onNodeClick={(_, n) => setSel({ kind: 'node', data: (n.data as any).raw })}
            onEdgeClick={(_, e) => setSel({ kind: 'edge', data: e.data })}>
            <Background />
            <Controls />
            <MiniMap pannable zoomable />
          </ReactFlow>
        </div>
        <p className="mt-2 text-xs text-text-muted">{q.data.nodes.length} nodes · {q.data.edges.length} edges. Every edge carries provenance — click one to see its source.</p>
      </div>
      <Card title={sel ? (sel.kind === 'node' ? sel.data.type : `Edge: ${sel.data.type}`) : 'Evidence panel'}>
        {!sel && <p className="text-sm text-text-muted">Click a node to see its evidence, or an edge to see its source.</p>}
        {sel?.kind === 'node' && (
          <div className="space-y-3 text-sm">
            <h3 className="font-semibold">{sel.data.data?.title || sel.data.label}</h3>
            <dl className="space-y-1 text-xs">
              {Object.entries(sel.data.data || {}).filter(([k]) => k !== 'title').map(([k, v]) => (
                <div key={k}><dt className="inline font-semibold">{k}: </dt><dd className="inline">{String(v)}</dd></div>
              ))}
            </dl>
            <div>
              <div className="label">Connections ({connected.length})</div>
              <ul className="space-y-1 text-xs">
                {connected.map((e: any) => (
                  <li key={e.id}><button className="text-left hover:underline" onClick={() => setSel({ kind: 'edge', data: e })}>
                    <Badge>{e.type}</Badge> {e.source === sel.data.id ? `→ ${label(e.target)}` : `← ${label(e.source)}`}
                  </button></li>
                ))}
              </ul>
            </div>
          </div>
        )}
        {sel?.kind === 'edge' && (
          <div className="space-y-2 text-sm">
            <p className="text-xs"><span className="font-semibold">{label(sel.data.source)}</span> —{sel.data.type}→ <span className="font-semibold">{label(sel.data.target)}</span></p>
            <div className="label">Provenance</div>
            <p className="font-medium">{sel.data.provenance.source}</p>
            {sel.data.provenance.section && <p className="text-xs text-text-secondary">{sel.data.provenance.section}</p>}
            {sel.data.provenance.passage && <blockquote className="border-l-2 border-gold pl-2 text-xs">“{sel.data.provenance.passage}”</blockquote>}
            {sel.data.provenance.detail && <p className="text-xs">{sel.data.provenance.detail}</p>}
            {sel.data.provenance.score != null && <p className="text-xs">Similarity {sel.data.provenance.score}</p>}
          </div>
        )}
      </Card>
    </div>
  );
}
