'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'next/navigation';
import { useState } from 'react';
import { Badge, Card, EmptyState, ErrorState, SeverityBadge, Spinner } from '@/components/ui';
import { patch } from '@/lib/api';
import { useInnovationData } from '@/lib/hooks';

export default function GapsTab() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const gaps = useInnovationData<any[]>(id, 'evidence-gaps');
  const risk = useInnovationData<any[]>(id, 'risk-map');
  const [sev, setSev] = useState('');
  const [cat, setCat] = useState('');
  const upd = useMutation({
    mutationFn: ({ gid, status }: { gid: string; status: string }) => patch(`/innovations/${id}/evidence-gaps/${gid}`, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['innovation', id] }),
  });
  const rows = (gaps.data || []).filter((g) => (!sev || g.severity === sev) && (!cat || g.category === cat));
  const cats = Array.from(new Set((gaps.data || []).map((g) => g.category)));

  return (
    <div className="space-y-6">
      <section>
        <h2 className="mb-3 font-serif text-2xl">Risk map</h2>
        {risk.isLoading && <Spinner />}
        {risk.isError && <ErrorState error={risk.error} onRetry={() => risk.refetch()} />}
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {risk.data?.map((r) => (
            <div key={r.category} className="flex flex-col rounded-lg border border-surface-border bg-surface-elevated p-3 text-xs">
              <div className="flex items-center justify-between"><h3 className="text-sm font-semibold">{r.category}</h3><SeverityBadge severity={r.severity} /></div>
              <p className="mt-2 font-medium">{r.risk}</p>
              <p className="mt-2 text-text-secondary"><span className="font-semibold">Why it matters:</span> {r.why_it_matters}</p>
              <p className="mt-1 text-text-secondary"><span className="font-semibold">Mitigation:</span> {r.mitigation}</p>
              {r.open_question && <p className="mt-1 text-text-secondary"><span className="font-semibold">Open question:</span> {r.open_question}</p>}
              {r.count > 1 && <p className="mt-1 text-text-muted">+{r.count - 1} related item(s)</p>}
              <p className="mt-auto pt-2 text-text-muted">Owner: {r.owner}</p>
            </div>
          ))}
        </div>
      </section>

      <Card title={`Evidence gaps (${gaps.data?.length ?? '…'})`} subtitle="Detected automatically from the profile, evidence, patents, classification and source freshness."
        actions={
          <div className="flex gap-2">
            <select className="py-1 text-xs" value={sev} onChange={(e) => setSev(e.target.value)} aria-label="Severity filter">
              <option value="">All severities</option>{['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((s) => <option key={s}>{s}</option>)}
            </select>
            <select className="py-1 text-xs" value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Category filter">
              <option value="">All categories</option>{cats.map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
        }>
        {gaps.isLoading && <Spinner />}
        {gaps.isError && <ErrorState error={gaps.error} onRetry={() => gaps.refetch()} />}
        {gaps.data && rows.length === 0 && <EmptyState title="No gaps match these filters" />}
        <ul className="divide-y divide-surface-border">
          {rows.map((g) => (
            <li key={g.id} className="grid gap-2 py-3 text-sm md:grid-cols-[110px_1fr_170px]">
              <div className="flex flex-col gap-1"><SeverityBadge severity={g.severity} /><Badge>{g.category}</Badge></div>
              <div>
                <p className={g.status === 'RESOLVED' || g.status === 'NOT_APPLICABLE' ? 'text-text-muted line-through' : ''}>{g.description}</p>
                <p className="mt-1 text-xs text-text-secondary">→ {g.recommended_action}</p>
              </div>
              <select className="h-8 py-1 text-xs" value={g.status} aria-label="Gap status" onChange={(e) => upd.mutate({ gid: g.id, status: e.target.value })}>
                {['OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'NOT_APPLICABLE'].map((s) => <option key={s}>{s}</option>)}
              </select>
            </li>
          ))}
        </ul>
        {upd.isError && <ErrorState error={upd.error} />}
      </Card>
    </div>
  );
}
