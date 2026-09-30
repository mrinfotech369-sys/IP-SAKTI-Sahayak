'use client';

import { useQuery } from '@tanstack/react-query';
import { Badge, ErrorState, FreshnessBadge, JurisdictionBadge, PageHeader, Spinner, TierBadge, fmtDate } from '@/components/ui';
import { get } from '@/lib/api';

export default function Sources() {
  const q = useQuery({ queryKey: ['sources'], queryFn: () => get<any[]>('/sources') });
  return (
    <div>
      <PageHeader title="Sources" subtitle="Configured source registry. Tier 1 = official law/regulator · 2 = international official · 3 = peer-reviewed · 4 = secondary/demo · 5 = user-provided/unverified. No unrestricted access to protected databases is claimed." />
      {q.isLoading && <Spinner />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      <div className="overflow-x-auto rounded-lg border border-surface-border bg-surface-elevated">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-muted text-xs text-text-secondary"><tr><th className="px-3 py-2">Source</th><th>Tier</th><th>Jurisdiction</th><th>Type</th><th>Access</th><th>Last checked</th><th>Status</th><th className="text-right pr-3">Docs</th></tr></thead>
          <tbody>
            {q.data?.map((s) => (
              <tr key={s.id} className="border-t border-surface-border align-top">
                <td className="px-3 py-2"><div className="font-medium">{s.name}</div><div className="text-xs text-text-muted">{s.authority}</div>{s.description && <div className="text-xs text-text-secondary">{s.description}</div>}</td>
                <td><TierBadge tier={s.authority_tier} /></td><td><JurisdictionBadge j={s.jurisdiction} /></td>
                <td className="text-xs">{s.source_type}</td>
                <td><Badge tone={s.access_level.startsWith('RESTRICTED') ? 'warn' : 'neutral'}>{s.access_level.replace(/_/g, ' ').toLowerCase()}</Badge></td>
                <td className="text-xs">{fmtDate(s.last_checked)}</td>
                <td>{s.active ? <FreshnessBadge status={s.status} /> : <Badge tone="danger">inactive</Badge>}</td>
                <td className="pr-3 text-right tabular-nums">{s.documents}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
