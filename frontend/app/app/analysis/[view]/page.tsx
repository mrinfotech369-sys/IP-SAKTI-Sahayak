'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { EmptyState, ErrorState, LinkButton, PageHeader, Spinner } from '@/components/ui';
import { get } from '@/lib/api';
import type { InnovationCard } from '@/lib/types';

const VIEWS: Record<string, [string, string, string]> = {
  evidence: ['Evidence Map', 'evidence', 'All evidence linked to an innovation, by type, jurisdiction and tier.'],
  graph: ['Evidence Graph', 'graph', 'Interactive graph of features, patents, studies, regulations and gaps with provenance on every edge.'],
  gaps: ['Evidence Gaps', 'gaps', 'Automatically detected missing evidence, by severity.'],
  risk: ['Risk Analysis', 'gaps', 'IP, regulatory, evidence, data, confidentiality, freshness, translation and classification risks.'],
};

export default function AnalysisChooser() {
  const { view } = useParams<{ view: string }>();
  const [title, tab, subtitle] = VIEWS[view] || VIEWS.evidence;
  const inns = useQuery({ queryKey: ['innovations'], queryFn: () => get<InnovationCard[]>('/innovations') });
  return (
    <div>
      <PageHeader eyebrow="Analysis" title={title} subtitle={`${subtitle} Choose an innovation.`} />
      {inns.isLoading && <Spinner />}
      {inns.isError && <ErrorState error={inns.error} onRetry={() => inns.refetch()} />}
      {inns.data?.length === 0 && <EmptyState title="No innovations yet" action={<LinkButton href="/app/innovations/new">Create innovation</LinkButton>} />}
      <ul className="grid gap-2 md:grid-cols-2">
        {inns.data?.map((i) => (
          <li key={i.id}>
            <Link href={`/app/innovations/${i.id}/${tab}`} className="flex items-center justify-between rounded-lg border border-surface-border bg-surface-elevated px-4 py-3 hover:border-green/50">
              <span className="font-medium">{i.name}</span>
              <span className="text-xs text-text-muted">{i.counts.evidence} evidence · {i.counts.evidence_gaps} gaps · {i.counts.patent_matches} patents</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
