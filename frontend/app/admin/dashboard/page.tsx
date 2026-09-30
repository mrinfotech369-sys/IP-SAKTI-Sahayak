'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { Badge, Button, Card, ErrorState, PageHeader, Spinner, Stat, fmtDateTime } from '@/components/ui';
import { get, post } from '@/lib/api';
import { useAdmin } from '@/lib/admin';

export default function AdminDashboard() {
  const { admin } = useAdmin();
  const ov = useQuery({ queryKey: ['admin-overview'], queryFn: () => get('/admin/overview'), refetchInterval: 30_000 });
  const purge = useMutation({ mutationFn: (dry: boolean) => post(`/admin/retention/run?dry_run=${dry}`) });
  const d = ov.data;

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Admin console" title={`Welcome, ${admin?.name.split(' ')[0]}`} subtitle="System-wide analytics and health — separate from any single workspace." />
      {ov.isError && <ErrorState error={ov.error} onRetry={() => ov.refetch()} />}
      {ov.isLoading && <Spinner />}
      {d && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
            {Object.entries(d.counts).map(([k, v]) => (
              <Stat key={k} label={k.replace(/_/g, ' ')} value={v as number}
                href={{ open_escalations: '/admin/escalations', open_feedback: '/admin/feedback', sources: '/admin/sources', documents: '/admin/documents',
                        users: '/admin/users', workspaces: '/admin/workspaces', sources_due_review: '/admin/documents', failed_ingestion_jobs: '/admin/documents' }[k]} />
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Language model">
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between"><dt>Provider</dt><dd>{d.llm.provider}</dd></div>
                <div className="flex justify-between"><dt>Status</dt><dd><Badge tone={d.llm.available ? 'ok' : 'warn'}>{d.llm.available ? 'connected' : 'extractive mode (no key)'}</Badge></dd></div>
              </dl>
            </Card>
            <Card title="Citations (all time)" actions={<Link href="/admin/citations" className="text-xs underline">Details →</Link>}>
              <dl className="space-y-1 text-sm">
                {Object.entries(d.citations.by_status).map(([k, v]) => <div key={k} className="flex justify-between"><dt>{k.toLowerCase().replace('_', ' ')}</dt><dd>{v as number}</dd></div>)}
                <div className="flex justify-between font-semibold"><dt>Unsupported rate</dt><dd>{d.citations.unsupported_rate}</dd></div>
              </dl>
            </Card>
            <Card title="Runtime (measured)">
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between"><dt>Queries sampled</dt><dd>{d.runtime.queries_sampled}</dd></div>
                <div className="flex justify-between"><dt>Latency p50 / p95</dt><dd>{d.runtime.latency_ms.p50 ?? '—'} / {d.runtime.latency_ms.p95 ?? '—'} ms</dd></div>
                <div className="flex justify-between"><dt>Avg cost / query</dt><dd>${d.runtime.avg_cost_per_query_usd}</dd></div>
              </dl>
            </Card>
          </div>

          {d.recent_errors?.length > 0 && (
            <Card title={`Recent system errors (${d.recent_errors.length})`} subtitle="Unhandled server errors since the process started.">
              <ul className="space-y-1 text-xs">
                {d.recent_errors.map((e: any, i: number) => (
                  <li key={i} className="flex justify-between gap-2 border-b border-surface-border py-1 last:border-0">
                    <span><Badge tone="danger">{e.error}</Badge> {e.method} {e.path}</span>
                    <span className="text-text-muted">{fmtDateTime(e.at)} · {e.request_id}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card title="Retention policy enforcement"
            actions={<>
              <Button size="sm" variant="secondary" onClick={() => purge.mutate(true)} loading={purge.isPending}>Dry run</Button>
              <Button size="sm" variant="danger" onClick={() => window.confirm('Delete conversations and uploads older than each workspace retention policy?') && purge.mutate(false)}>Apply</Button>
            </>}>
            {!purge.data && <p className="text-sm text-text-muted">Deletes conversations and workspace uploads older than each workspace&apos;s retention policy. Audit logs are always kept.</p>}
            {purge.data && (
              <ul className="space-y-1 text-xs">
                {(purge.data as any).workspaces.map((w: any) => (
                  <li key={w.workspace}>{(purge.data as any).dry_run ? 'Would delete' : 'Deleted'} {w.conversations} conversations, {w.uploaded_documents} uploads — {w.workspace} ({w.policy})</li>
                ))}
              </ul>
            )}
          </Card>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
            {[
              ['Users', '/admin/users'], ['Source Registry', '/admin/sources'], ['Documents', '/admin/documents'],
              ['RAG Monitoring', '/admin/rag'], ['Citation Verification', '/admin/citations'], ['Escalations', '/admin/escalations'],
              ['Audit Logs', '/admin/audit-logs'], ['Settings', '/admin/settings'],
            ].map(([label, href]) => (
              <Link key={href} href={href} className="rounded-lg border border-surface-border bg-surface-elevated px-4 py-3 font-medium hover:border-green/50">{label} →</Link>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
