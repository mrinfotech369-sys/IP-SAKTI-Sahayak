'use client';

import { useQuery } from '@tanstack/react-query';
import { Download } from 'lucide-react';
import { useState } from 'react';
import { Badge, Button, ErrorState, PageHeader, Spinner, fmtDateTime } from '@/components/ui';
import { get } from '@/lib/api';

export default function AdminAuditLogs() {
  const [category, setCategory] = useState('');
  const [action, setAction] = useState('');
  const [user, setUser] = useState('');
  const [days, setDays] = useState(30);
  const params = new URLSearchParams({ days: String(days), ...(category && { category }), ...(action && { action }), ...(user && { user }) }).toString();
  const q = useQuery({ queryKey: ['admin-audit-logs', params], queryFn: () => get<any[]>(`/admin/audit-logs?${params}`) });
  const categories = ['auth', 'admin', 'source', 'document', 'escalation', 'export'];

  return (
    <div>
      <PageHeader eyebrow="Admin console" title="Audit Logs" subtitle="User actions, admin actions, source and document changes, escalation actions, authentication events and exports — across every workspace."
        actions={
          <a href={`/api/admin/audit-logs/export?${params}`} target="_blank" rel="noreferrer">
            <Button variant="secondary"><Download className="h-4 w-4" /> Export CSV</Button>
          </a>
        } />
      <div className="mb-4 flex flex-wrap gap-2 text-sm">
        <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category"><option value="">All categories</option>{categories.map((c) => <option key={c} value={c}>{c}</option>)}</select>
        <input placeholder="Exact action…" value={action} onChange={(e) => setAction(e.target.value)} aria-label="Action" />
        <input placeholder="User name or email…" value={user} onChange={(e) => setUser(e.target.value)} aria-label="User" />
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Time window"><option value={7}>7 days</option><option value={30}>30 days</option><option value={90}>90 days</option><option value={365}>1 year</option></select>
      </div>
      {q.isLoading && <Spinner />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      <ol className="relative ml-3 border-l border-surface-border">
        {q.data?.map((a: any) => (
          <li key={a.id} className="mb-3 ml-4">
            <span className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full border-2 border-darkbg bg-green" />
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge tone="dark">{a.action}</Badge><span className="font-medium">{a.user || 'System'}</span>
              {a.email && <span className="text-xs text-text-muted">{a.email}</span>}
              {a.workspace && <Badge tone="info">{a.workspace}</Badge>}
              {a.entity_type && <span className="text-xs text-text-muted">{a.entity_type} {a.entity_id?.slice(0, 8)}</span>}
            </div>
            <div className="text-xs text-text-muted">{fmtDateTime(a.created_at)}{a.request_id ? ` · req ${a.request_id}` : ''}</div>
            {Object.keys(a.metadata || {}).length > 0 && <pre className="mt-1 max-w-3xl overflow-x-auto rounded bg-surface-muted p-1.5 text-[10px]">{JSON.stringify(a.metadata)}</pre>}
          </li>
        ))}
      </ol>
      {q.data?.length === 0 && <p className="text-sm text-text-muted">No matching audit events.</p>}
    </div>
  );
}
