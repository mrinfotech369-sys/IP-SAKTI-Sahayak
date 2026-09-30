'use client';

import { useParams } from 'next/navigation';
import { useMemo, useState } from 'react';
import { EvidenceCard, SourceDrawer } from '@/components/evidence';
import { EmptyState, ErrorState, Spinner, Tabs } from '@/components/ui';
import { useInnovationData } from '@/lib/hooks';
import type { Evidence } from '@/lib/types';

const TYPES = [['ALL', 'All'], ['REGULATORY', 'Regulatory'], ['IP', 'IP / Patent law'], ['TK', 'TK & ABS'], ['SCIENTIFIC', 'Scientific']];

export default function EvidenceTab() {
  const { id } = useParams<{ id: string }>();
  const q = useInnovationData<any[]>(id, 'evidence');
  const [type, setType] = useState('ALL');
  const [jur, setJur] = useState('');
  const [tier, setTier] = useState('');
  const [open, setOpen] = useState<Evidence | null>(null);

  const items: Evidence[] = useMemo(
    () => (q.data || []).map((e: any) => ({
      ...e, n: 0, tier: e.authority_tier, rerank_score: e.relevance, methods: [], injection_flag: false,
      freshness: e.superseded ? 'Superseded' : e.last_checked ? 'Current' : 'Unknown',
      why_retrieved: `${e.why_retrieved || ''}${e.added_by === 'USER' ? ' · added by user' : ''} · applicability: ${e.applicability.replace('_', ' ').toLowerCase()}`,
    })),
    [q.data]
  );
  const rows = items.filter((e: any) => (type === 'ALL' || e.evidence_type === type) && (!jur || e.jurisdiction === jur) && (!tier || String(e.tier) === tier));
  const counts = Object.fromEntries(TYPES.map(([k]) => [k, k === 'ALL' ? items.length : items.filter((e: any) => e.evidence_type === k).length]));

  return (
    <div>
      <Tabs tabs={TYPES.map(([k, l]) => ({ key: k, label: `${l} (${counts[k] ?? 0})` }))} active={type} onChange={setType} />
      <div className="my-3 flex flex-wrap gap-2 text-sm">
        <select value={jur} onChange={(e) => setJur(e.target.value)} aria-label="Jurisdiction filter">
          <option value="">All jurisdictions</option>
          {['IN', 'US', 'AU', 'INTERNATIONAL'].map((j) => <option key={j}>{j}</option>)}
        </select>
        <select value={tier} onChange={(e) => setTier(e.target.value)} aria-label="Tier filter">
          <option value="">All tiers</option>
          {[1, 2, 3, 4, 5].map((t) => <option key={t} value={t}>Tier {t}</option>)}
        </select>
      </div>
      {q.isLoading && <Spinner label="Loading evidence…" />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && rows.length === 0 && <EmptyState title="No evidence for these filters">Re-run analysis or add passages from the Research Assistant.</EmptyState>}
      <div className="grid gap-3 lg:grid-cols-2">
        {rows.map((e) => <EvidenceCard key={(e as any).id} e={e} onOpen={setOpen} compact />)}
      </div>
      <SourceDrawer evidence={open} onClose={() => setOpen(null)} />
    </div>
  );
}
