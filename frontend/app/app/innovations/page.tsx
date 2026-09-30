'use client';

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { InnovationCardView } from '@/components/innovation-card';
import { EmptyState, ErrorState, LinkButton, PageHeader, Spinner } from '@/components/ui';
import { get } from '@/lib/api';
import { useApp } from '@/lib/providers';
import type { InnovationCard } from '@/lib/types';

export default function Innovations() {
  const { t } = useApp();
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const inns = useQuery({ queryKey: ['innovations'], queryFn: () => get<InnovationCard[]>('/innovations') });
  const rows = (inns.data || []).filter((i) => (!q || i.name.toLowerCase().includes(q.toLowerCase())) && (!status || i.status === status));
  return (
    <div>
      <PageHeader title={t.nav.allInnovations} subtitle="Every innovation in this workspace, with evidence, prior-art and gap counts." actions={<LinkButton href="/app/innovations/new">{t.nav.createInnovation}</LinkButton>} />
      <div className="mb-4 flex flex-wrap gap-2">
        <input placeholder="Filter by name…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter by name" />
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
          <option value="">All statuses</option>
          {['DRAFT', 'PROFILED', 'IN_RESEARCH', 'IN_REVIEW', 'COMPLETED'].map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      {inns.isLoading && <Spinner />}
      {inns.isError && <ErrorState error={inns.error} onRetry={() => inns.refetch()} />}
      {inns.data && rows.length === 0 && (
        <EmptyState title={inns.data.length ? 'No innovations match these filters' : 'No innovations yet'} action={<LinkButton href="/app/innovations/new">{t.nav.createInnovation}</LinkButton>} />
      )}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {rows.map((i) => <InnovationCardView key={i.id} inn={i} />)}
      </div>
    </div>
  );
}
