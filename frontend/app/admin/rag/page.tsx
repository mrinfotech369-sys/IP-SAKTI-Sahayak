'use client';

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Badge, Card, ErrorState, JurisdictionBadge, PageHeader, Spinner, Stat, fmtDateTime } from '@/components/ui';
import { get } from '@/lib/api';

export default function RagMonitoring() {
  const [days, setDays] = useState(30);
  const q = useQuery({ queryKey: ['admin-rag', days], queryFn: () => get(`/admin/rag?days=${days}`) });
  const d: any = q.data;
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Admin console" title="RAG / Retrieval Monitoring" subtitle="Retrieval statistics, failed retrievals, abstentions, latency and system errors."
        actions={<select className="text-xs" value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Time window">
          <option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option>
        </select>} />
      {q.isLoading && <Spinner />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {d && (
        <>
          <p className="text-xs text-text-muted">{d.privacy_note}</p>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
            <Stat label="Queries" value={d.queries} />
            <Stat label="Abstention rate" value={d.abstention_rate} />
            <Stat label="Failed retrieval rate" value={d.failed_retrieval_rate} />
            <Stat label="LLM fallbacks" value={d.llm_fallbacks} hint="extractive fallback used" />
            <Stat label="Latency p50" value={`${d.latency_ms.p50 ?? '—'} ms`} />
            <Stat label="Latency p95" value={`${d.latency_ms.p95 ?? '—'} ms`} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="By evidence status">
              <dl className="space-y-1 text-sm">{Object.entries(d.by_evidence_status).map(([k, v]) => <div key={k} className="flex justify-between"><dt>{k}</dt><dd>{v as number}</dd></div>)}</dl>
            </Card>
            <Card title="By generation mode">
              <dl className="space-y-1 text-sm">{Object.entries(d.by_generation_mode).map(([k, v]) => <div key={k} className="flex justify-between"><dt>{k}</dt><dd>{v as number}</dd></div>)}</dl>
            </Card>
            <Card title="By intent">
              <dl className="space-y-1 text-xs">{Object.entries(d.by_intent).map(([k, v]) => <div key={k} className="flex justify-between"><dt>{k}</dt><dd>{v as number}</dd></div>)}</dl>
            </Card>
            <Card title="Abstention reasons">
              <dl className="space-y-1 text-sm">{Object.entries(d.abstention_reasons).map(([k, v]) => <div key={k} className="flex justify-between"><dt>{k}</dt><dd>{v as number}</dd></div>)}</dl>
            </Card>
          </div>
          <Card title={`Failed retrievals (${d.failed_retrievals.length})`} subtitle="No relevant evidence found for these questions.">
            {d.failed_retrievals.length === 0 && <p className="text-sm text-text-muted">None in this window.</p>}
            <ul className="space-y-2 text-xs">{d.failed_retrievals.map((f: any, i: number) => (
              <li key={i} className="border-b border-surface-border pb-2 last:border-0">
                <div className="flex flex-wrap items-center gap-2"><Badge tone="danger">{f.reason}</Badge>{f.jurisdiction && <JurisdictionBadge j={f.jurisdiction} />}<span className="text-text-muted">{fmtDateTime(f.at)}</span></div>
                <p className="mt-1">{f.question}</p>
                {f.missing && <p className="text-text-secondary">Missing: {f.missing}</p>}
              </li>
            ))}</ul>
          </Card>
          <Card title={`Abstentions with some evidence (${d.abstentions.length})`} subtitle="Evidence was found but claims could not be verified, or the request was refused for safety reasons.">
            <ul className="space-y-2 text-xs">{d.abstentions.map((f: any, i: number) => (
              <li key={i} className="border-b border-surface-border pb-2 last:border-0">
                <div className="flex flex-wrap items-center gap-2"><Badge tone="warn">{f.reason}</Badge>{f.jurisdiction && <JurisdictionBadge j={f.jurisdiction} />}<span className="text-text-muted">{fmtDateTime(f.at)}</span></div>
                <p className="mt-1">{f.question}</p>
              </li>
            ))}</ul>
          </Card>
          {d.system_errors.length > 0 && (
            <Card title={`System errors (${d.system_errors.length})`}>
              <ul className="space-y-1 text-xs">{d.system_errors.map((e: any, i: number) => (
                <li key={i} className="flex justify-between"><span><Badge tone="danger">{e.error}</Badge> {e.method} {e.path}</span><span className="text-text-muted">{fmtDateTime(e.at)}</span></li>
              ))}</ul>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
