'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { Badge, Card, ErrorState, PageHeader, SeverityBadge, Spinner, fmtDateTime } from '@/components/ui';
import { BackLink } from '@/components/back';
import { get, patch } from '@/lib/api';

export default function EscalationView() {
  const { eid } = useParams<{ eid: string }>();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['escalation', eid], queryFn: () => get(`/escalations/${eid}`) });
  const upd = useMutation({ mutationFn: (status: string) => patch(`/escalations/${eid}`, { status }), onSuccess: () => qc.invalidateQueries({ queryKey: ['escalation', eid] }) });
  if (q.isLoading) return <Spinner />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const e = q.data;
  const p = e.packet;
  return (
    <div className="space-y-4">
      <div className="flex gap-4"><BackLink href="/app/escalations">All escalations</BackLink><BackLink href={`/app/innovations/${e.innovation_id}/review`}>Back to innovation</BackLink></div>
      <PageHeader eyebrow="Escalation packet" title={e.type.replace('_', ' ')} subtitle={e.summary}
        actions={
          <label className="text-xs">Status{' '}
            <select value={e.status} onChange={(ev) => upd.mutate(ev.target.value)} aria-label="Escalation status">
              {['OPEN', 'IN_REVIEW', 'RESOLVED', 'CLOSED'].map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
        } />
      {upd.isError && <ErrorState error={upd.error} />}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Request">
          <p className="text-sm">{e.reason}</p>
          <p className="mt-2 text-xs text-text-secondary">Recommended professional: <span className="font-semibold">{e.recommended_professional}</span></p>
          <p className="mt-1 text-xs text-text-muted">Created {fmtDateTime(e.created_at)}</p>
          <Link href={`/app/innovations/${e.innovation_id}`} className="mt-2 inline-block text-xs underline">Open innovation: {p.innovation_summary.name}</Link>
        </Card>
        <Card title="Open questions" className="lg:col-span-2">
          <ul className="ml-4 list-disc space-y-1 text-sm">{e.open_questions.map((x: string) => <li key={x}>{x}</li>)}</ul>
        </Card>
      </div>
      <Card title="Technical features"><div className="flex flex-wrap gap-1">{p.technical_features.map((f: any) => <Badge key={f.name} tone="info">{f.type}: {f.name}</Badge>)}</div></Card>
      <Card title={`Patent findings (${p.patent_findings.families.length} families)`} subtitle={p.patent_findings.review_note}>
        <ul className="space-y-1 text-sm">{p.patent_findings.families.map((f: any) => <li key={f.family_id}><span className="font-mono">{f.family_id}</span> — {f.representative.title} ({f.jurisdictions.join(', ')}) · matched {f.matched_features.join(', ')}</li>)}</ul>
      </Card>
      <Card title="Regulatory findings">
        <ul className="space-y-1 text-sm">{Object.values(p.regulatory_findings.passport).map((x: any) => <li key={x.jurisdiction}><span className="font-semibold">{x.country}:</span> {x.possible_pathway} (provisional, {x.confidence})</li>)}</ul>
      </Card>
      <Card title={`Evidence gaps (${p.evidence_gaps.length})`}>
        <ul className="space-y-1 text-sm">{p.evidence_gaps.map((g: any) => <li key={g.id} className="flex gap-2"><SeverityBadge severity={g.severity} /> {g.description}</li>)}</ul>
      </Card>
      {p.conflicting_sources.length > 0 && (
        <Card title="Conflicting sources">
          {p.conflicting_sources.map((c: any) => (
            <div key={c.topic} className="grid gap-2 text-sm md:grid-cols-2">
              <div className="rounded border border-surface-border p-2"><div className="font-semibold">{c.source_a.title}</div><div>{c.source_a.position}</div><div className="text-xs text-text-muted">effective {c.source_a.effective_date}</div></div>
              <div className="rounded border border-surface-border p-2"><div className="font-semibold">{c.source_b.title}</div><div>{c.source_b.position}</div><div className="text-xs text-text-muted">effective {c.source_b.effective_date}</div></div>
            </div>
          ))}
        </Card>
      )}
      <Card title={`Citations (${p.citations.length})`}>
        <ul className="space-y-1 text-xs">{p.citations.map((c: any, i: number) => <li key={i}>{c.title} — {c.authority} {c.section ? `· ${c.section}` : ''} <span className="text-text-muted">[{c.review_status}]</span></li>)}</ul>
      </Card>
      <Card title="Audit trail">
        <ul className="space-y-1 text-xs">{p.audit_trail.map((a: any, i: number) => <li key={i}>{fmtDateTime(a.at)} — {a.action}</li>)}</ul>
      </Card>
      <p className="text-xs text-text-muted">{p.boundary}</p>
    </div>
  );
}
