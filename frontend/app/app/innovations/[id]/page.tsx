'use client';

import Link from 'next/link';
import { useParams, useSearchParams } from 'next/navigation';
import { Badge, Card, ErrorState, FreshnessBadge, Notice, SeverityBadge, Spinner, fmtDateTime } from '@/components/ui';
import { useInnovationData } from '@/lib/hooks';

function Step({ n, title, children, href }: { n: number; title: string; children: React.ReactNode; href?: string }) {
  return (
    <section className="rounded-lg border border-surface-border bg-surface-elevated">
      <header className="flex items-center justify-between border-b border-surface-border px-4 py-2.5">
        <h2 className="flex items-center gap-2 text-sm font-semibold"><span className="grid h-6 w-6 place-items-center rounded-full bg-deep-green text-xs text-white">{n}</span>{title}</h2>
        {href && <Link href={href} className="text-xs underline">Details →</Link>}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

export default function SummaryTab() {
  const { id } = useParams<{ id: string }>();
  const created = useSearchParams().get('created');
  const q = useInnovationData(id, 'summary');
  if (q.isLoading) return <Spinner label="Assembling analysis…" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const s = q.data;
  const base = `/app/innovations/${id}`;
  return (
    <div className="space-y-4">
      {created && <Notice tone="ok" title="Innovation created">Profile generated and first analysis complete. Review the Profile tab and confirm anything marked “Needs confirmation”.</Notice>}
      <Step n={1} title="Classification (provisional)" href={`${base}/classification`}>
        <div className="grid gap-3 md:grid-cols-3">
          {s.classification.map((c: any) => (
            <div key={c.jurisdiction} className="rounded border border-surface-border p-3 text-sm">
              <div className="text-xs uppercase tracking-wider text-text-muted">{c.country}</div>
              <div className="font-semibold">{c.category || 'Undetermined'}</div>
              <div className="text-xs text-text-secondary">confidence {c.confidence} · heuristic{c.alternatives.length ? ` · alt: ${c.alternatives.join(', ')}` : ''}</div>
              <Badge tone="warn" className="mt-1">Human review required</Badge>
            </div>
          ))}
        </div>
      </Step>
      <Step n={2} title="Regulatory pathway" href={`${base}/regulatory`}>
        <div className="grid gap-3 md:grid-cols-3">
          {s.regulatory_pathway.map((r: any) => (
            <div key={r.jurisdiction} className="rounded border border-surface-border p-3 text-xs">
              <div className="flex items-center justify-between"><span className="font-semibold">{r.country}</span><FreshnessBadge status={r.freshness} /></div>
              <div className="mt-1">{r.authority}</div>
              <div className="text-text-muted">{r.framework}</div>
              <ul className="ml-4 mt-1 list-disc">{r.key_requirements.map((x: string) => <li key={x}>{x}</li>)}</ul>
            </div>
          ))}
        </div>
      </Step>
      <Step n={3} title="IP considerations" href={`${base}/patents`}>
        <div className="mb-2 flex flex-wrap gap-2 text-xs">
          <Badge tone="gold">{s.ip_considerations.patent_families} overlapping patent families</Badge>
          <Badge tone="gold">{s.ip_considerations.feature_overlaps} feature-level overlaps</Badge>
          <Badge tone="warn" title="TKDL was not searched — no TKDL conclusion is implied">{s.ip_considerations.tkdl_access.label}</Badge>
        </div>
        <table className="w-full text-left text-xs">
          <thead className="text-text-muted"><tr><th className="py-1">Flag</th><th>Provision</th><th>Issue</th><th>Why flagged</th></tr></thead>
          <tbody>{s.ip_considerations.provisions.map((p: any) => (
            <tr key={p.id} className="border-t border-surface-border align-top">
              <td className="py-1.5"><SeverityBadge severity={p.severity === 'INFO' ? 'LOW' : p.severity} /></td>
              <td className="font-medium">{p.instrument} — {p.provision}{p.document_id && <Link className="ml-1 text-info underline" href={`/app/documents/${p.document_id}`}>source</Link>}</td>
              <td>{p.issue}</td><td className="text-text-secondary">{p.why_flagged}</td>
            </tr>
          ))}</tbody>
        </table>
        <p className="mt-2 text-[11px] text-text-muted">{s.ip_considerations.boundary}</p>
      </Step>
      <Step n={4} title={`Evidence (${s.evidence.total})`} href={`${base}/evidence`}>
        <div className="flex flex-wrap gap-2 text-xs">{Object.entries(s.evidence.by_type).map(([k, v]) => <Badge key={k}>{k}: {v as number}</Badge>)}</div>
        <ul className="mt-2 space-y-1 text-xs">{s.evidence.top.map((e: any) => <li key={e.id}><span className="font-medium">{e.title}</span>{e.section ? ` · ${e.section}` : ''} <span className="text-text-muted">(Tier {e.authority_tier})</span></li>)}</ul>
      </Step>
      <Step n={5} title="Next steps" href={`${base}/review`}>
        <ol className="space-y-2 text-sm">{s.next_steps.map((n: any, i: number) => (
          <li key={i} className="flex gap-2"><SeverityBadge severity={n.severity} /><div><div>{n.action}</div><div className="text-xs text-text-muted">Because: {n.because}</div></div></li>
        ))}</ol>
      </Step>
      {s.history.length > 0 && (
        <Card title="Analysis history" subtitle="Each run records the source versions it relied on (reproducible evidence trail).">
          <ul className="space-y-2 text-xs">{s.history.map((h: any) => (
            <li key={h.at}><details><summary className="cursor-pointer">{fmtDateTime(h.at)} · {h.latency_ms} ms · {h.source_versions.length} source versions</summary>
              <ul className="ml-4 mt-1 list-disc">{h.source_versions.map((v: any) => <li key={v.title}>{v.title} — {v.version || '—'}, effective {v.effective_date || '—'}, checked {fmtDateTime(v.last_checked)}</li>)}</ul>
            </details></li>
          ))}</ul>
        </Card>
      )}
    </div>
  );
}
