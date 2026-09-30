'use client';

import { useQuery } from '@tanstack/react-query';
import { ExternalLink } from 'lucide-react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { Badge, Card, DemoBadge, ErrorState, FreshnessBadge, JurisdictionBadge, PageHeader, Spinner, TierBadge, fmtDate } from '@/components/ui';
import { get } from '@/lib/api';

export default function DocumentView() {
  const { did } = useParams<{ did: string }>();
  const q = useQuery({ queryKey: ['document', did], queryFn: () => get(`/documents/${did}`) });
  if (q.isLoading) return <Spinner />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  return (
    <div>
      <Link href="/app/documents" className="text-xs text-text-muted hover:underline">← Documents</Link>
      <PageHeader title={d.title} subtitle={`${d.source} · ${d.authority}`} />
      <div className="mb-4 flex flex-wrap gap-1.5"><TierBadge tier={d.tier} /><JurisdictionBadge j={d.jurisdiction} /><Badge>{d.document_type}</Badge><FreshnessBadge status={d.freshness} /><DemoBadge reviewStatus={d.review_status} /></div>
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Card title={`Passages (${d.chunks.length})`} subtitle="Structure-aware chunks: sections, definitions, requirements, claims">
          <div className="space-y-2">
            {d.chunks.map((c: any) => (
              <div key={c.id} className="rounded border border-surface-border p-3 text-sm">
                <div className="mb-1 flex flex-wrap gap-1 text-xs"><span className="font-semibold">{c.section || `Passage ${c.index + 1}`}</span>{c.subsection && <span className="text-text-muted">· {c.subsection}</span>}<Badge>{c.chunk_type.toLowerCase()}</Badge>{c.injection_flag && <Badge tone="danger">instruction-like text — treated as data</Badge>}</div>
                <p>{c.content}</p>
              </div>
            ))}
          </div>
        </Card>
        <Card title="Metadata">
          <dl className="space-y-1.5 text-xs">
            {[['Publication', d.publication_date], ['Effective', d.effective_date], ['Version', d.version], ['Last checked', fmtDate(d.last_checked)], ['Language', d.language], ['Access', d.access_level],
              ['Extraction', d.extraction_method], ['OCR confidence', d.ocr_confidence ?? 'n/a'], ['Review status', d.review_status], ['Content hash', d.content_hash?.slice(0, 16)],
              ['Supersedes', d.supersedes ? 'yes' : '—'], ['Superseded by', d.superseded_by ? 'yes — do not treat as current' : '—']].map(([k, v]) => (
              <div key={k as string} className="flex justify-between gap-2"><dt className="text-text-muted">{k}</dt><dd className="text-right font-medium">{v || '—'}</dd></div>
            ))}
          </dl>
          {d.url && <a href={d.url} target="_blank" rel="noopener noreferrer" className="mt-3 inline-flex items-center gap-1 text-xs text-info underline">Official source <ExternalLink className="h-3 w-3" /></a>}
          {d.source_description && <p className="mt-3 text-xs text-text-secondary">{d.source_description}</p>}
        </Card>
      </div>
    </div>
  );
}
