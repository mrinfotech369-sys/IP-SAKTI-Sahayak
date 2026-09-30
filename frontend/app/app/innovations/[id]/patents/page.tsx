'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'next/navigation';
import { useState } from 'react';
import { PatentCard } from '@/components/evidence';
import { Badge, Card, EmptyState, ErrorState, JurisdictionBadge, Notice, Spinner, Tabs } from '@/components/ui';
import { patch } from '@/lib/api';
import { useInnovationData } from '@/lib/hooks';

export default function PatentsTab() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const q = useInnovationData(id, 'patents');
  const [view, setView] = useState('matrix');
  const [feature, setFeature] = useState('');
  const [jur, setJur] = useState('');
  const [minSim, setMinSim] = useState(0);
  const [after, setAfter] = useState('');
  const review = useMutation({
    mutationFn: ({ matchId, status }: { matchId: string; status: string }) => patch(`/innovations/${id}/patents/matches/${matchId}`, { review_status: status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['innovation', id, 'patents'] }),
  });

  if (q.isLoading) return <Spinner label="Searching patent literature…" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  const features = Array.from(new Set(d.matrix.map((m: any) => m.feature))) as string[];
  const rows = d.matrix.filter((m: any) => (!feature || m.feature === feature) && (!jur || m.jurisdiction === jur) && m.similarity >= minSim && (!after || (m.date || '') >= after));

  return (
    <div className="space-y-4">
      <Notice tone="warn">{d.review_note} Patent records in this demo corpus are fictional (DEMO-…) and exist only to demonstrate the workflow.</Notice>
      <Card title="Generated search concepts" subtitle="Keywords, synonyms, botanical and chemical names per technical feature">
        <div className="grid gap-2 md:grid-cols-2">
          {d.search_concepts.map((c: any) => (
            <div key={c.feature_id} className="rounded border border-surface-border p-2 text-xs">
              <div className="flex items-center gap-2"><Badge tone="info">{c.feature_type}</Badge><span className="font-medium">{c.feature}</span></div>
              <div className="mt-1 text-text-secondary">keywords: {c.keywords.join(', ') || '—'}</div>
              {c.synonyms.length > 0 && <div className="text-text-secondary">synonyms: {c.synonyms.join(', ')}</div>}
            </div>
          ))}
        </div>
      </Card>
      <Tabs tabs={[{ key: 'matrix', label: `Feature matrix (${d.matrix.length})` }, { key: 'families', label: `Patent families (${d.families.length})` }]} active={view} onChange={setView} />
      {view === 'matrix' && (
        <>
          <div className="flex flex-wrap items-end gap-2 text-sm">
            <select value={feature} onChange={(e) => setFeature(e.target.value)} aria-label="Feature filter">
              <option value="">All features</option>
              {features.map((f) => <option key={f}>{f}</option>)}
            </select>
            <select value={jur} onChange={(e) => setJur(e.target.value)} aria-label="Jurisdiction filter">
              <option value="">All jurisdictions</option>
              {['IN', 'US', 'EP', 'AU'].map((j) => <option key={j}>{j}</option>)}
            </select>
            <label className="text-xs">Min similarity
              <input type="range" min={0} max={1} step={0.05} value={minSim} onChange={(e) => setMinSim(Number(e.target.value))} className="ml-2 align-middle" /> {minSim.toFixed(2)}
            </label>
            <label className="text-xs">Priority after <input type="date" value={after} onChange={(e) => setAfter(e.target.value)} className="ml-1 py-1" /></label>
          </div>
          {rows.length === 0 ? <EmptyState title="No feature-level overlaps for these filters" /> : (
            <div className="overflow-x-auto rounded-lg border border-surface-border bg-surface-elevated">
              <table className="w-full text-left text-xs">
                <thead className="bg-surface-muted text-text-secondary">
                  <tr><th className="px-3 py-2">Innovation feature</th><th>Document</th><th>Passage</th><th>Date</th><th>Jurisdiction</th><th className="text-right">Similarity</th><th className="px-3">Review</th></tr>
                </thead>
                <tbody>
                  {rows.map((m: any) => (
                    <tr key={m.match_id} className="border-t border-surface-border align-top">
                      <td className="px-3 py-2"><Badge tone="info">{m.feature_type}</Badge><div className="mt-1 font-medium">{m.feature}</div></td>
                      <td className="py-2"><div className="font-mono">{m.publication_number}</div><div className="text-text-secondary">{m.document}</div><div className="text-text-muted">family {m.family_id}</div></td>
                      <td className="max-w-md py-2">“{m.passage.slice(0, 220)}{m.passage.length > 220 ? '…' : ''}”<div className="mt-1 text-text-muted">matched: {m.matched_terms.join(', ')}</div></td>
                      <td className="py-2">{m.date}</td>
                      <td className="py-2"><JurisdictionBadge j={m.jurisdiction} /></td>
                      <td className="py-2 text-right tabular-nums">{m.similarity.toFixed(2)}</td>
                      <td className="px-3 py-2">
                        <select className="py-0.5 text-xs" value={m.review_status} aria-label="Review status" onChange={(e) => review.mutate({ matchId: m.match_id, status: e.target.value })}>
                          <option value="PENDING">Pending review</option>
                          <option value="REVIEWED_RELEVANT">Relevant</option>
                          <option value="REVIEWED_NOT_RELEVANT">Not relevant</option>
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {review.isError && <ErrorState error={review.error} />}
        </>
      )}
      {view === 'families' && (
        <div className="space-y-4">
          {d.families.length === 0 && <EmptyState title="No patent families matched" />}
          {d.families.map((f: any) => (
            <Card key={f.family_id} title={<>Patent family <span className="font-mono">{f.family_id}</span></>}
              subtitle={`${f.members.length} member(s): ${f.jurisdictions.join(', ')} · best similarity ${f.best_score.toFixed(2)} · matched: ${f.matched_features.join(', ')}`}>
              <div className="space-y-3">{f.members.map((p: any) => <PatentCard key={p.patent_id} p={p} />)}</div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
