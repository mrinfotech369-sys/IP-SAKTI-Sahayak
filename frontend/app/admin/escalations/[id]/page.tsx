'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'next/navigation';
import { FormEvent, useState } from 'react';
import { BackButton } from '@/components/back';
import { Badge, Card, ErrorState, PageHeader, SeverityBadge, Spinner, fmtDateTime } from '@/components/ui';
import { get, patch } from '@/lib/api';

export default function AdminEscalationDetail() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['admin-escalation', id], queryFn: () => get(`/admin/escalations/${id}`) });
  const [note, setNote] = useState('');
  const upd = useMutation({
    mutationFn: (body: any) => patch(`/admin/escalations/${id}`, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-escalation', id] }); setNote(''); },
  });
  if (q.isLoading) return <Spinner />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const e: any = q.data;
  const p = e.packet;

  return (
    <div className="space-y-4">
      <BackButton fallback="/admin/escalations" />
      <PageHeader eyebrow="Admin console — Escalation" title={e.type.replace(/_/g, ' ')} subtitle={e.summary}
        actions={
          <label className="text-xs">Status{' '}
            <select value={e.status} onChange={(ev) => upd.mutate({ status: ev.target.value })} aria-label="Escalation status">
              {['OPEN', 'IN_REVIEW', 'RESOLVED', 'CLOSED'].map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
        } />
      {upd.isError && <ErrorState error={upd.error} />}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Request">
          <p className="text-sm">{e.reason}</p>
          <p className="mt-2 text-xs text-text-secondary">Recommended professional: <span className="font-semibold">{e.recommended_professional}</span></p>
          <p className="mt-1 text-xs text-text-muted">Workspace: {e.workspace} · Innovation: {e.innovation_name}</p>
          <p className="mt-1 text-xs text-text-muted">Created {fmtDateTime(e.created_at)}</p>
        </Card>
        <Card title="Assign reviewer" className="lg:col-span-2">
          <div className="flex flex-wrap items-center gap-2">
            <select className="text-sm" value={e.assigned_to?.id || ''} onChange={(ev) => (ev.target.value ? upd.mutate({ assigned_to: ev.target.value }) : upd.mutate({ unassign: true }))} aria-label="Assign reviewer">
              <option value="">Unassigned</option>
              {e.eligible_reviewers.map((r: any) => <option key={r.id} value={r.id}>{r.name} ({r.email})</option>)}
            </select>
            {e.assigned_to && <Badge tone="info">Currently: {e.assigned_to.name}</Badge>}
          </div>
          <p className="mt-2 text-xs text-text-muted">Only Reviewers, Admins or Owners of this innovation&apos;s workspace can be assigned.</p>

          <div className="mt-4">
            <div className="label">Reviewer notes ({e.reviewer_notes.length})</div>
            <ul className="space-y-2 text-xs">{e.reviewer_notes.map((n: any, i: number) => (
              <li key={i} className="rounded bg-surface-muted p-2"><div className="font-semibold">{n.by} · {fmtDateTime(n.at)}</div><p>{n.note}</p></li>
            ))}</ul>
            <form onSubmit={(ev: FormEvent) => { ev.preventDefault(); if (note.trim()) upd.mutate({ note }); }} className="mt-2 flex gap-2">
              <input className="flex-1" placeholder="Add a reviewer note…" value={note} onChange={(ev) => setNote(ev.target.value)} aria-label="New note" />
              <button type="submit" className="rounded-md bg-deep-green px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50" disabled={!note.trim() || upd.isPending}>Add note</button>
            </form>
          </div>
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
              <div className="rounded border border-surface-border p-2"><div className="font-semibold">{c.source_a.title}</div><div>{c.source_a.position}</div></div>
              <div className="rounded border border-surface-border p-2"><div className="font-semibold">{c.source_b.title}</div><div>{c.source_b.position}</div></div>
            </div>
          ))}
        </Card>
      )}
      <Card title={`Citations (${p.citations.length})`}>
        <ul className="space-y-1 text-xs">{p.citations.map((c: any, i: number) => <li key={i}>{c.title} — {c.authority} {c.section ? `· ${c.section}` : ''} <span className="text-text-muted">[{c.review_status}]</span></li>)}</ul>
      </Card>
      <p className="text-xs text-text-muted">{p.boundary}</p>
    </div>
  );
}
