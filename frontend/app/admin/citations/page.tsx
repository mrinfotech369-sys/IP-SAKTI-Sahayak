'use client';

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Badge, Card, ErrorState, PageHeader, Spinner, Stat, SupportBadge, fmtDateTime } from '@/components/ui';
import { get } from '@/lib/api';

export default function CitationMonitoring() {
  const [days, setDays] = useState(30);
  const q = useQuery({ queryKey: ['admin-citations', days], queryFn: () => get(`/admin/citations?days=${days}`) });
  const d: any = q.data;
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Admin console" title="Citation Verification Monitoring" subtitle="Whether cited evidence actually supports the claims the assistant makes."
        actions={<select className="text-xs" value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Time window">
          <option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option>
        </select>} />
      {q.isLoading && <Spinner />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {d && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Claims checked" value={d.claims} />
            <Stat label="Supported rate" value={d.supported_rate} />
            <Stat label="Unsupported rate" value={d.unsupported_rate} />
            <Stat label="Conflicting rate" value={d.conflicting_rate} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="By status">
              <dl className="space-y-1 text-sm">{Object.entries(d.by_status).map(([k, v]) => <div key={k} className="flex items-center justify-between"><dt><SupportBadge status={k} /></dt><dd>{v as number}</dd></div>)}</dl>
            </Card>
            <Card title="By claim type">
              <dl className="space-y-1 text-sm">{Object.entries(d.by_claim_type).map(([k, v]) => <div key={k} className="flex justify-between"><dt>{k}</dt><dd>{v as number}</dd></div>)}</dl>
            </Card>
          </div>
          <Card title={`Verification failures (${d.failures.length})`} subtitle="Unsupported, conflicting or insufficiently-evidenced claims.">
            {d.failures.length === 0 && <p className="text-sm text-text-muted">None in this window.</p>}
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-text-secondary"><tr><th className="py-1">When</th><th>Status</th><th>Type</th><th>Claim</th><th>Cited document</th><th>Score</th><th>Entailment</th></tr></thead>
                <tbody>{d.failures.map((f: any, i: number) => (
                  <tr key={i} className="border-t border-surface-border align-top">
                    <td className="py-1.5 whitespace-nowrap">{fmtDateTime(f.at)}</td>
                    <td><SupportBadge status={f.status} /></td>
                    <td><Badge>{f.claim_type}</Badge></td>
                    <td className="max-w-sm">{f.claim}{f.notes && <div className="text-text-muted">{f.notes}</div>}</td>
                    <td className="max-w-xs">{f.cited_document || '—'}</td>
                    <td className="tabular-nums">{f.score ?? '—'}</td>
                    <td>{f.llm_entailment || '—'}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
