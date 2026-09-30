'use client';

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Badge, ErrorState, PageHeader, Spinner, fmtDateTime } from '@/components/ui';
import { get } from '@/lib/api';

export default function Audit() {
  const [action, setAction] = useState('');
  const q = useQuery({ queryKey: ['audit', action], queryFn: () => get<any[]>(`/audit${action ? `?action=${action}` : ''}`) });
  const actions = ['login', 'innovation_created', 'innovation_updated', 'profile_generated', 'search_started', 'search_completed', 'document_viewed', 'citation_verified',
    'report_generated', 'report_exported', 'escalation_created', 'source_modified', 'document_ingested', 'workspace_setting_changed'];
  return (
    <div>
      <PageHeader title="Audit Trail" subtitle="Every significant action in this workspace. IP addresses are stored only as salted hashes; confidential text is never logged." actions={
        <select value={action} onChange={(e) => setAction(e.target.value)} aria-label="Action filter"><option value="">All actions</option>{actions.map((a) => <option key={a}>{a}</option>)}</select>} />
      {q.isLoading && <Spinner />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      <ol className="relative ml-3 border-l border-surface-border">
        {q.data?.map((a) => (
          <li key={a.id} className="mb-3 ml-4">
            <span className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full border-2 border-darkbg bg-green" />
            <div className="flex flex-wrap items-center gap-2 text-sm"><Badge tone="dark">{a.action}</Badge><span className="font-medium">{a.user || 'System'}</span>{a.entity_type && <span className="text-xs text-text-muted">{a.entity_type} {a.entity_id?.slice(0, 8)}</span>}</div>
            <div className="text-xs text-text-muted">{fmtDateTime(a.created_at)}{a.request_id ? ` · req ${a.request_id}` : ''}</div>
            {Object.keys(a.metadata || {}).length > 0 && <pre className="mt-1 max-w-3xl overflow-x-auto rounded bg-surface-muted p-1.5 text-[10px]">{JSON.stringify(a.metadata)}</pre>}
          </li>
        ))}
      </ol>
    </div>
  );
}
